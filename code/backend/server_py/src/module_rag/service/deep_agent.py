"""业务侧深度取证(REQ-019 设计 §3.3): 工具构建 + 证据融合

分层边界(设计 §3.1):
- 循环本体委托通用有界执行器 `module_agent.service.agent_runner.AgentRunner`(业务无关),
  本文件**不实现**轮次/预算/超时控制;
- 本文件只做业务: 构建工具(知识库 / 联网 / Skill 句柄)、把工具结果转成证据、
  证据排序(RRF 融合 + Rerank 精排)、产出注入回答节点的上下文。

与 Skill 层的关系:
- 知识库与联网在 Skill 层已有 `sys.rag_qa` / `sys.web_search`, 但它们只回文本,
  拿不到结构化片段做证据融合与引用溯源; 故取证由原生工具 kb_search / web_search
  承担(结构化证据), Skill 句柄只注册其余能力, 避免同一能力重复占工具位。
- Skill 句柄走 `module_agent.skills.adapter.build_gated_tools` 条件注册(能力/权限/开关),
  连续失败 2 次由会话级熔断器摘除并下发 skill_masked 事件(§5.4)。
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from module_agent.service.agent_runner import AgentRunner, ModeConfig
from module_agent.service.skill_runtime import SkillContext
from module_agent.skills.adapter import (
    FEATURE_KNOWLEDGE_BASE,
    FEATURE_WEB,
    ToolGate,
    build_gated_tools,
)
from module_agent.skills.breaker import SkillCircuitBreaker
from module_agent.skills.registry import list_manifests
from module_rag.do.project_document_chunk import (
    ProjectDocumentChunkSearchResponse,
    SearchRequest,
)
from module_rag.do.rag_chat import WebCitation
from module_rag.service.project_document_chunk import ProjectDocumentChunkService

logger = logging.getLogger(__name__)

#: RRF 平滑常数(标准取值 60, 越小越强调头部排名)
_RRF_K = 60
#: 单条工具结果回传给模型的片段数与单片段长度
_TOOL_RESULT_SNIPPETS = 5
_TOOL_RESULT_PREVIEW = 240
#: 注入回答上下文的单条 Skill 输出长度
_SKILL_CONTEXT_PREVIEW = 2000
#: 注入回答上下文的 Skill 输出条数
_SKILL_CONTEXT_KEEP = 3
#: 已由原生工具覆盖的 Skill(避免同一能力重复注册两个工具)
_NATIVE_TOOL_SKILLS = {"sys.rag_qa", "sys.web_search"}


class KbSearchArgs(BaseModel):
    """知识库检索工具参数"""

    query: str = Field(description="用于向量/语义检索的查询语句, 尽量具体")
    top_k: int = Field(default=5, description="返回片段数量, 1~10")


class WebSearchArgs(BaseModel):
    """联网检索工具参数"""

    query: str = Field(description="用于联网搜索的查询语句")
    limit: int = Field(default=5, description="返回条数, 1~10")


@dataclass
class _EvidenceCollector:
    """深度取证证据池(设计 §3.3)"""

    #: 知识库片段(结构化, 可引用溯源)
    kb_chunks: list[ProjectDocumentChunkSearchResponse] = field(default_factory=list)
    #: 联网引用
    web_candidates: list[WebCitation] = field(default_factory=list)
    #: Skill 产出(工具名, 文本)
    skill_outputs: list[tuple[str, str]] = field(default_factory=list)
    #: Skill 熔断等过程事件
    skill_events: list[dict] = field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        """是否已取到可引用证据"""
        return bool(self.kb_chunks or self.web_candidates)


class DeepAgentRunner:
    """深度取证(业务侧): 构建工具 → 有界 ReAct 取证 → 证据融合排序"""

    def __init__(
        self,
        project_document_chunk_service: ProjectDocumentChunkService | None = None,
        agent_runner: AgentRunner | None = None,
    ):
        self.project_document_chunk_service = (
            project_document_chunk_service or ProjectDocumentChunkService()
        )
        self.agent_runner = agent_runner or AgentRunner()

    # ################ 主入口 ################

    async def run(
        self,
        llm: Any,
        *,
        user_id: str,
        project_ids: list[str],
        messages: list[Any],
        mode_config: Any,
        enable_websearch: bool = False,
        conversation_id: str | None = None,
        query: str = "",
        rerank_limit: int = 20,
    ) -> dict:
        """执行深度取证

        :param llm: 对话模型(需支持 bind_tools)
        :param mode_config: 内置 Agent 的模式参数(ChatModeConfig)
        :return: dict(deep_evidence, deep_events, deep_stop_reason,
                     knowledge_context_list, web_results, skill_context)
        """
        collector = _EvidenceCollector()
        cfg = self._to_mode_config(mode_config)

        tools = await self._build_tools(
            user_id=user_id,
            project_ids=project_ids,
            enable_websearch=enable_websearch,
            conversation_id=conversation_id,
            collector=collector,
        )

        result = await self.agent_runner.run(llm, messages, tools, cfg)

        deep_events = list(result.events) + list(collector.skill_events)
        kb_chunks, web_candidates = await self._fuse_evidence(
            user_id=user_id,
            query=query,
            collector=collector,
            rerank_limit=rerank_limit,
        )

        return {
            "deep_evidence": self._evidence_summary(kb_chunks, web_candidates, collector),
            "deep_events": deep_events,
            "deep_stop_reason": str(result.stop_reason),
            "knowledge_context_list": kb_chunks,
            "web_results": web_candidates,
            "skill_context": self._format_skill_context(collector.skill_outputs),
        }

    # ################ 工具构建 ################

    async def _build_tools(
        self,
        *,
        user_id: str,
        project_ids: list[str],
        enable_websearch: bool,
        conversation_id: str | None,
        collector: _EvidenceCollector,
    ) -> list[BaseTool]:
        """按会话可用能力构建工具清单(能力/权限/开关不满足即不注册)"""
        tools: list[BaseTool] = []
        reserved: set[str] = set()

        if project_ids:
            tools.append(self._kb_tool(user_id, project_ids, collector))
            reserved.add("kb_search")
        if enable_websearch:
            tools.append(self._web_tool(collector))
            reserved.add("web_search")

        tools.extend(
            await self._skill_tools(
                user_id=user_id,
                project_ids=project_ids,
                conversation_id=conversation_id,
                collector=collector,
                reserved=reserved,
            )
        )
        return tools

    def _kb_tool(
        self,
        user_id: str,
        project_ids: list[str],
        collector: _EvidenceCollector,
    ) -> BaseTool:
        """知识库检索工具(结果进证据池, 不进对话流)"""

        async def kb_search(query: str, top_k: int = 5) -> str:
            limit = max(1, min(int(top_k or 5), 10))
            request = SearchRequest(
                project_ids=project_ids,
                query_content=query,
                keyword_query=query,
                limit=max(limit * 3, 20),
                rerank_limit=limit,
                enable_rerank=False,
            )
            try:
                chunks = await self.project_document_chunk_service.search(request, user_id)
            except Exception as e:
                logger.warning(f"深度取证知识库检索失败: {e}")
                return f"知识库检索失败: {e}"
            collector.kb_chunks.extend(chunks)
            return self._format_chunks(chunks, limit)

        return StructuredTool.from_function(
            coroutine=kb_search,
            name="kb_search",
            description="检索企业内部知识库, 返回与查询最相关的文档片段",
            args_schema=KbSearchArgs,
        )

    def _web_tool(self, collector: _EvidenceCollector) -> BaseTool:
        """联网检索工具(结果进证据池, 不进对话流)"""

        async def web_search(query: str, limit: int = 5) -> str:
            from module_websearch.config.settings import get_websearch_settings
            from module_websearch.service.websearch import WebSearchService
            from module_websearch.utils.websearch.do.websearch import (
                SearchRequest as WSSearchRequest,
            )

            try:
                settings = await get_websearch_settings()
                response = await WebSearchService().search(
                    WSSearchRequest(
                        query=query,
                        limit=max(1, min(int(limit or 5), 10)),
                    )
                )
            except Exception as e:
                logger.warning(f"深度取证联网检索失败: {e}")
                return f"联网检索失败: {e}"
            candidates = [
                WebCitation(
                    title=item.title,
                    url=item.url,
                    source=item.source,
                    description=item.description,
                )
                for item in response.results
            ]
            collector.web_candidates.extend(candidates)
            return self._format_web(candidates)

        return StructuredTool.from_function(
            coroutine=web_search,
            name="web_search",
            description="联网搜索公开网页, 返回与查询最相关的网页内容",
            args_schema=WebSearchArgs,
        )

    async def _skill_tools(
        self,
        *,
        user_id: str,
        project_ids: list[str],
        conversation_id: str | None,
        collector: _EvidenceCollector,
        reserved: set[str],
    ) -> list[BaseTool]:
        """注册 Skill 句柄为工具(条件注册 + 会话级熔断)"""
        manifests = [
            m for m in list_manifests(agent_callable_only=True)
            if m.uid not in _NATIVE_TOOL_SKILLS
        ]
        if not manifests:
            return []

        capability_keys: set[str] = set()
        for manifest in manifests:
            capability_keys.update(manifest.required_capabilities)
            capability_keys.update(manifest.optional_capabilities)
            for group in manifest.capability_alternatives:
                capability_keys.update(group)
        available = await self._available_capabilities(user_id, capability_keys)

        features: set[str] = set()
        if project_ids:
            features.add(FEATURE_KNOWLEDGE_BASE)
        if reserved and "web_search" in reserved:
            features.add(FEATURE_WEB)

        ctx = SkillContext(
            user_id=user_id,
            project_ids=list(project_ids),
            conversation_id=conversation_id,
            priority_class="interactive",
            entry="agent",
        )

        async def _on_mask(uid: str, reason: str) -> None:
            collector.skill_events.append(
                {
                    "type": "skill_masked",
                    "tool_name": uid,
                    "content": f"技能 {uid} 连续失败, 已在本次执行中摘除",
                    "data": {"skill_key": uid, "reason": reason},
                }
            )

        breaker = SkillCircuitBreaker(on_mask=_on_mask)
        registration = await build_gated_tools(
            [m.uid for m in manifests],
            ctx,
            ToolGate(
                features=features,
                available_capabilities=available,
                project_ids=list(project_ids),
            ),
            breaker=breaker,
        )

        tools: list[BaseTool] = []
        for tool in registration.tools:
            if tool.name in reserved:
                continue
            reserved.add(tool.name)
            tools.append(self._wrap_recording(tool, collector))
        return tools

    def _wrap_recording(self, tool: BaseTool, collector: _EvidenceCollector) -> BaseTool:
        """给 Skill 工具套一层记录器: 产出进证据池(与检索证据区分)"""

        async def _run(**kwargs: Any) -> str:
            text = await tool.ainvoke(kwargs)
            body = str(text or "")
            collector.skill_outputs.append((tool.name, body))
            return body

        return StructuredTool.from_function(
            coroutine=_run,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )

    # ################ 证据融合 ################

    async def _fuse_evidence(
        self,
        *,
        user_id: str,
        query: str,
        collector: _EvidenceCollector,
        rerank_limit: int,
    ) -> tuple[list[ProjectDocumentChunkSearchResponse], list[WebCitation]]:
        """证据 RRF 融合 → Rerank 精排 → 按类型拆回两份结果"""
        if not collector.has_evidence:
            return [], []

        fused = self._rrf_fuse(collector.kb_chunks, collector.web_candidates)
        if not fused:
            return [], []

        rerank_llm = await self._get_rerank_llm(user_id)
        if rerank_llm is None:
            return self._split(fused)

        try:
            merged = await self.project_document_chunk_service.rerank_candidates(
                rerank_llm, query, fused, rerank_limit
            )
        except Exception as e:
            logger.warning(f"深度取证证据精排失败, 使用 RRF 顺序: {e}")
            return self._split(fused)
        return self._split(merged)

    @staticmethod
    def _rrf_fuse(
        kb_chunks: list[ProjectDocumentChunkSearchResponse],
        web_candidates: list[WebCitation],
    ) -> list[Any]:
        """RRF 融合(Reciprocal Rank Fusion): 多路召回按名次倒数加权合并"""
        scored: list[tuple[str, float, Any]] = []
        for rank, chunk in enumerate(kb_chunks, start=1):
            scored.append((f"kb:{chunk.id}", 1.0 / (_RRF_K + rank), chunk))
        for rank, item in enumerate(web_candidates, start=1):
            key = f"web:{item.url or item.title}"
            scored.append((key, 1.0 / (_RRF_K + rank), item))
        scored.sort(key=lambda entry: entry[1], reverse=True)
        for _, score, obj in scored:
            if hasattr(obj, "score"):
                obj.score = score
        return [obj for _, _, obj in scored]

    @staticmethod
    def _split(items: list[Any]) -> tuple[list[ProjectDocumentChunkSearchResponse], list[WebCitation]]:
        """融合结果按类型拆回知识片段与网络引用"""
        kb = [item for item in items if isinstance(item, ProjectDocumentChunkSearchResponse)]
        web = [item for item in items if isinstance(item, WebCitation)]
        return kb, web

    async def _get_rerank_llm(self, user_id: str) -> Any:
        """取用户 Rerank 模型(不可用时返回 None, 退化为 RRF 顺序)"""
        from module_ai.utils.llm.types import ModelType
        from module_rag.service.user_model import UserModelService

        try:
            return await UserModelService().get_llm_by_user_id(
                user_id, False, ModelType.RERANK
            )
        except Exception as e:
            logger.warning(f"取 Rerank 模型失败: {e}")
            return None

    @staticmethod
    async def _available_capabilities(user_id: str, keys: set[str]) -> set[str]:
        """解析能力键 → 可用能力集合(不可用即不注册依赖该能力的 Skill)"""
        from module_ai.service.capability_registry import resolve as resolve_capability

        available: set[str] = set()
        for key in keys:
            try:
                resolved = await resolve_capability(key, user_id)
            except Exception as e:
                logger.debug(f"能力解析失败 {key}: {e}")
                continue
            if resolved.available:
                available.add(key)
        return available

    # ################ 输出格式化 ################

    @staticmethod
    def _evidence_summary(
        kb_chunks: list[ProjectDocumentChunkSearchResponse],
        web_candidates: list[WebCitation],
        collector: _EvidenceCollector,
    ) -> list[dict]:
        """证据摘要(结构化, 供前端/观测消费)"""
        items: list[dict] = []
        for chunk in kb_chunks:
            content = (getattr(chunk, "content", "") or "").replace("\n", " ")
            items.append(
                {
                    "kind": "kb",
                    "source": getattr(chunk, "source", "") or "未知来源",
                    "document_id": getattr(chunk, "document_id", None),
                    "chunk_id": getattr(chunk, "id", None),
                    "score": getattr(chunk, "score", None),
                    "summary": content[:120] + ("…" if len(content) > 120 else ""),
                }
            )
        for item in web_candidates:
            items.append(
                {
                    "kind": "web",
                    "source": item.source or item.url,
                    "title": item.title,
                    "url": item.url,
                    "score": item.score,
                    "summary": (item.description or "")[:120],
                }
            )
        for name, body in collector.skill_outputs:
            items.append(
                {
                    "kind": "skill",
                    "source": name,
                    "summary": body[:120] + ("…" if len(body) > 120 else ""),
                }
            )
        return items

    @staticmethod
    def _format_chunks(chunks: list[ProjectDocumentChunkSearchResponse], limit: int) -> str:
        """知识片段格式化(回传模型的预览文本)"""
        if not chunks:
            return "知识库未检索到相关片段"
        lines: list[str] = []
        for index, chunk in enumerate(chunks[:limit], start=1):
            source = getattr(chunk, "source", "") or f"片段{index}"
            content = (getattr(chunk, "content", "") or "")[:_TOOL_RESULT_PREVIEW]
            lines.append(f"[{index}] {source}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_web(candidates: list[WebCitation]) -> str:
        """网络引用格式化(回传模型的预览文本)"""
        if not candidates:
            return "联网搜索未检索到相关网页"
        lines: list[str] = []
        for index, candidate in enumerate(candidates[:_TOOL_RESULT_SNIPPETS], start=1):
            title = candidate.title or candidate.url or f"网页{index}"
            content = (candidate.description or "")[:_TOOL_RESULT_PREVIEW]
            lines.append(f"[{index}] {title}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_skill_context(outputs: list[tuple[str, str]]) -> str:
        """Skill 产出格式化为回答上下文(与检索证据区分, 模型知道它是技能产物)"""
        if not outputs:
            return ""
        lines: list[str] = []
        for name, content in outputs[-_SKILL_CONTEXT_KEEP:]:
            body = (content or "")[:_SKILL_CONTEXT_PREVIEW]
            lines.append(f"### 技能 {name}\n{body}")
        return "\n\n".join(lines)

    # ################ 预算映射 ################

    @staticmethod
    def _to_mode_config(mode_config: Any) -> ModeConfig:
        """内置 Agent 的模式参数 → 通用执行器预算(业务无关, 只做字段搬运)"""
        get = mode_config.get if isinstance(mode_config, dict) else lambda key, default=None: getattr(mode_config, key, default)
        think_level = str(get("think_level", "off") or "off")
        return ModeConfig(
            max_loops=int(get("max_loops", 6) or 6),
            max_model_calls=int(get("max_model_calls", 8) or 8),
            max_tool_calls=int(get("max_tool_calls", 12) or 12),
            wall_clock_s=int(get("wall_clock_s", 90) or 90),
            think_level_plan=think_level,
            think_level_answer="off",
        )
