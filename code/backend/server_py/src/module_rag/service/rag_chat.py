"""
基于 LangGraph 的 RAG 聊天服务
- AsyncPostgresSaver 做上下文历史管理 (checkpointer)
- StateGraph: 意图分析 → 知识库检索 → LLM 对话
- 流式输出按事件类型分类: AGENT_THINKING / TOOL_CALL / LLM_THINKING / ANSWER / STATUS / ERROR
- 对话总结: 压缩历史 + 生成标题
"""

import asyncio
import logging
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.schema import StreamEvent
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from module_ai.service.llm import LLMService
from module_ai.utils.llm.types import RoleType, ModelType
from module_ai.utils.llm.chat.trim import messages_trim_with_max_tokens
from module_ai.utils.llm.limits import count_tokens, messages_tokens
from common.utils.fastapi_ex.exceptions import BusinessError
# 模式即 Agent(REQ-019 §2.2): 两级模式解析器 + 内置对话 Agent 档位配置
from module_agent.agents.builtin import ChatModeConfig, resolve_mode_config
from module_agent.service.mode_policy import (
    ExecMode,
    IntentSignal,
    ModeDecision,
    ModeSignals,
    RequestedMode,
    ToolAvailability,
    resolve_mode,
)
from module_ai.utils.llm.chat.think import with_think_mode
from module_rag.config.checkpointer import get_checkpointer
from module_rag.dao.rag_chat_prompt import (
    RAG_CHAT_SYSTEM_PROMPT,
    RAG_CHAT_SYSTEM_PROMPT_TEMPLATE,
    RAG_SUPPLEMENT_CONTEXT_TEMPLATE,
    RAG_WEB_CONTEXT_TEMPLATE,
    RAG_SKILL_CONTEXT_TEMPLATE,
    DEEP_AGENT_SYSTEM_PROMPT,
    INTENT_ANALYSIS_SYSTEM_PROMPT,
    SUMMARIZE_SYSTEM_PROMPT,
)
from module_rag.do.chat_message import ChatMessageCreate
from module_rag.do.conversation import ChatRequest, ConversationUpdate
from module_rag.do.rag_chat import (
    ConversationSummary,
    InteractionKind,
    InteractionOption,
    InteractionSpec,
    RagChatState,
    RagHelpInfo,
    StreamEventType,
    StreamOne,
    SummaryState,
    GraphNode,
    WebCitation,
)
from module_rag.service.chat_message import ChatMessageService
from module_rag.service.chat_attachment import get_temp_kb
from module_rag.service.conversation import ConversationService
from module_rag.service.conversation_title import maybe_auto_title
from module_rag.service.user_model import UserModelService
from module_rag.service.usage import ChatUsageService
from module_rag.do.project_document_chunk import (
    ProjectDocumentChunkSearchResponse,
    SearchRequest,
)
from module_rag.service.project_document_chunk import ProjectDocumentChunkService
# 业务侧深度取证(REQ-019 §3.3): 构建工具 + 证据融合
from module_rag.service.deep_agent import DeepAgentRunner
# 联网检索: 仅依赖 module_websearch 的 service 门面与配置读取入口(跨模块边界约定)
from module_websearch.config.settings import get_websearch_settings
from module_websearch.service.websearch import WebSearchService
from module_websearch.utils.websearch.do.websearch import SearchRequest as WSSearchRequest
from module_rag.utils.llm.stream_classifier import StreamEventClassifier

logger = logging.getLogger(__name__)

# ── 问答附件限制(附件入库个人默认临时知识库, 见 service/chat_attachment.py) ──
TEMP_MAX_FILES = 5  # 单条消息最多附件数


class RagChatService:
    """RAG 聊天服务 (基于 LangGraph)"""

    def __init__(
        self,
        llm_service: LLMService | None = None,
        user_model_service: UserModelService | None = None,
        chat_message_service: ChatMessageService | None = None,
        project_document_chunk_service: ProjectDocumentChunkService | None = None,
        conversation_service: ConversationService | None = None,
    ):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.llm_service = llm_service or LLMService()
        self.user_model_service = user_model_service or UserModelService()
        self.chat_message_service = chat_message_service or ChatMessageService()
        self.project_document_chunk_service = project_document_chunk_service or ProjectDocumentChunkService()
        self.conversation_service = conversation_service or ConversationService()
        self.chat_compiled_graph: CompiledStateGraph | None = None
        self.summary_compiled_graph: CompiledStateGraph | None = None
        self._classifier = StreamEventClassifier()
        # 深度取证(业务侧): 工具构建 + 证据融合, 循环本体委托通用有界执行器
        self._deep_runner = DeepAgentRunner(
            project_document_chunk_service=self.project_document_chunk_service
        )

    # ──────────────────────────────────────────────
    # Graph 初始化
    # ──────────────────────────────────────────────

    async def _init_compiled_graphs(self) -> None:
        """编译 chat / summary 两个 graph，checkpointer 按 thread_id 隔离会话"""
        checkpointer = await get_checkpointer()
        self.chat_compiled_graph = self._build_chat_graph().compile(
            checkpointer=checkpointer
        )
        self.summary_compiled_graph = self._build_summary_graph().compile(
            checkpointer=checkpointer
        )

    async def _resolve_auto_projects(self, user_id: str) -> list[str]:
        """自动知识库范围: 解析当前用户可见的知识库项目(与列表接口同口径)

        上限 500 条(与分页参数上限一致); 解析失败按"本轮不检索知识库"降级,
        不阻塞对话(用户仍可手动指定知识库)。
        """
        try:
            from common.utils.db.schema.pagination import PaginationParams
            from module_rag.service.project import ProjectService

            res = await ProjectService().list_paged(
                PaginationParams(page=1, size=500), viewer_id=user_id
            )
            return [p.id for p in res.items]
        except Exception as exc:
            logger.warning(f"自动知识库范围解析失败, 本轮不检索知识库: {exc}")
            return []

    # ──────────────────────────────────────────────
    # Chat Graph
    # ──────────────────────────────────────────────

    def _build_chat_graph(self) -> StateGraph:
        """构建聊天 graph:
        [intent_analysis] → (需澄清?) [clarify_interaction] → END
                          → [resolve_mode](模式解析) → (需检索?) [knowledge_search]
                          → (无结果?) [knowledge_gap] → END
                          → (deep?) [deep_agent](有界 ReAct 取证) → [chat] → END
                          → [chat] → END
        交互节点为"伪中断": 本次 run 结束并落 pending_interaction,
        用户下一条消息携带 interaction_response 续跑(经 checkpointer 共享 state)
        """

        graph = StateGraph(RagChatState)
        graph.add_node(GraphNode.INTENT, self._intent_analysis_node)
        graph.add_node(GraphNode.RESOLVE_MODE, self._resolve_mode_node)
        graph.add_node(GraphNode.SEARCH, self._knowledge_search_node)
        graph.add_node(GraphNode.DEEP, self._deep_agent_node)
        graph.add_node(GraphNode.CHAT, self._chat_node)
        graph.add_node(GraphNode.CLARIFY, self._clarify_interaction_node)
        graph.add_node(GraphNode.GAP, self._knowledge_gap_node)

        # 条件路由(起点): 知识缺口响应(supplement/answer_directly)跳过意图与检索直接对话;
        # 有知识库 → 意图分析; 否则直接进模式解析
        graph.add_conditional_edges(START, self._route_start)
        # 条件路由: 意图分析判定需要澄清 → 澄清交互; 其余一律进模式解析(产出 exec_mode)
        graph.add_conditional_edges(GraphNode.INTENT, self._route_after_intent)
        # 条件路由: 模式解析后需要外部信息且有知识库 → 检索; 否则直接对话
        graph.add_conditional_edges(GraphNode.RESOLVE_MODE, self._route_after_resolve_mode)
        # 条件路由: 检索正常但无结果 → 知识缺口交互(邀请用户补充缺失内容);
        # deep 模式先做多轮取证再决定是否真的缺内容
        graph.add_conditional_edges(GraphNode.SEARCH, self._route_after_search)
        # 条件路由: 深度取证后仍无证据 → 知识缺口交互; 否则直接对话
        graph.add_conditional_edges(GraphNode.DEEP, self._route_after_deep)
        graph.add_edge(GraphNode.CHAT, END)
        graph.add_edge(GraphNode.CLARIFY, END)
        graph.add_edge(GraphNode.GAP, END)
        return graph

    @staticmethod
    def _route_start(state: RagChatState) -> GraphNode:
        """起点路由: 知识缺口交互的补充/直接回答响应直接进对话节点, 其余按常规流程"""
        resp = state.get("interaction_response")
        if (
            isinstance(resp, dict)
            and resp.get("kind") == InteractionKind.KNOWLEDGE_GAP
            and resp.get("action") in ("supplement", "answer_directly")
        ):
            return GraphNode.CHAT
        return GraphNode.INTENT if state.get("project_ids") else GraphNode.RESOLVE_MODE

    @staticmethod
    def _route_after_intent(state: RagChatState) -> GraphNode:
        """意图分析后的路由: 信息不足→澄清交互; 其余→模式解析(§2.2)"""
        info: RagHelpInfo | None = state.get("rag_help_info")
        # 同一轮待澄清请求只问一次(防止响应后仍判定需澄清造成循环打断)
        pending = state.get("pending_interaction")
        already_asked = isinstance(pending, dict) and pending.get("kind") == InteractionKind.CLARIFY
        if (
            info
            and info.needs_clarification
            and info.clarify_question
            and not already_asked
        ):
            return GraphNode.CLARIFY
        return GraphNode.RESOLVE_MODE

    @staticmethod
    def _route_after_resolve_mode(state: RagChatState) -> GraphNode:
        """模式解析后的路由: 需外部信息且有知识库→检索; 否则直接对话"""
        info: RagHelpInfo | None = state.get("rag_help_info")
        need_search = bool(state.get("project_ids")) and bool(
            info and info.is_need_external_info
        )
        return GraphNode.SEARCH if need_search else GraphNode.CHAT

    @staticmethod
    def _route_after_search(state: RagChatState) -> GraphNode:
        """检索后路由: 知识库与网络均无命中(且检索未失败) → 知识缺口交互

        例外: kb_auto_only(用户未显式选择知识库, 仅临时库自动并入检索范围)时
        零命中降级直接回答 —— 临时库常驻检索范围, 不能让纯聊天一直触发知识缺口交互

        deep 模式: 零命中不立即打断用户, 先进深度取证(换关键词多轮检索),
        取证后仍无证据才回到知识缺口交互
        """
        has_knowledge = bool(state.get("knowledge_context_list") or [])
        has_web = bool(state.get("web_results") or [])
        if not state.get("search_error") and not has_knowledge and not has_web:
            if state.get("kb_auto_only"):
                return GraphNode.CHAT
            if state.get("exec_mode") == "deep":
                return GraphNode.DEEP
            return GraphNode.GAP
        if state.get("exec_mode") == "deep":
            return GraphNode.DEEP
        return GraphNode.CHAT

    @staticmethod
    def _route_after_deep(state: RagChatState) -> GraphNode:
        """深度取证后路由: 仍无任何证据 → 知识缺口交互; 否则进回答节点"""
        has_evidence = bool(state.get("knowledge_context_list") or []) or bool(
            state.get("web_results") or []
        )
        if not has_evidence and not state.get("kb_auto_only") and not state.get("search_error"):
            return GraphNode.GAP
        return GraphNode.CHAT

    async def _intent_analysis_node(self, state: RagChatState) -> dict:
        """意图分析: 提取检索关键词 & 判断是否需要外部知识"""
        user_id: str = state["user_id"]
        llm = await self.user_model_service.get_llm_by_user_id(user_id, streaming=False)
        messages: list[AnyMessage] = state["messages"]

        last_content = messages[-1].content if messages else ""
        if llm is None:
            # 无可用模型: 跳过意图分析, 用原问题检索(chat 节点会给出明确报错)
            logger.warning(f"用户 {user_id} 无可用对话模型, 意图分析跳过")
            rag_help_info = RagHelpInfo(
                intent=last_content,
                vector_search=last_content,
                full_text_search=last_content,
                web_search=last_content,
            )
        else:
            try:
                structured_llm = llm.with_structured_output(RagHelpInfo)
                rag_help_info: RagHelpInfo = await structured_llm.ainvoke(
                    [SystemMessage(content=INTENT_ANALYSIS_SYSTEM_PROMPT)] + messages
                )
                # 逐路兜底: 模型漏产出的 query 以原问题补位, 保证三路召回都有输入
                rag_help_info.vector_search = (
                    rag_help_info.vector_search or last_content
                )
                rag_help_info.full_text_search = (
                    rag_help_info.full_text_search or last_content
                )
                rag_help_info.web_search = (
                    rag_help_info.web_search or rag_help_info.vector_search
                )
            except Exception as e:
                logger.warning(f"意图分析失败，回退原问题: {e}")
                rag_help_info = RagHelpInfo(
                    intent=last_content,
                    vector_search=last_content,
                    full_text_search=last_content,
                    web_search=last_content,
                )
        return {"rag_help_info": rag_help_info}

    # ──────────────────────────────────────────────
    # 模式解析(REQ-019 §2.2)
    # ──────────────────────────────────────────────

    async def _resolve_mode_node(self, state: RagChatState) -> dict:
        """模式解析: 智能体(agent_key) + 意图信号 + 工具可用性 → exec_mode + mode_reason

        内置对话智能体是唯一入口(会话页只提供两者):
        - builtin_fast(快速): 固定 RAG 流程, 恒为 fast 档(模型关思考, 固定检索轮次)
        - builtin_thinking(思考): ReAct 有界多轮, 有工具时恒为 deep 档(模型开思考)
        其余/未选智能体沿用通用解析器(兼容旧客户端)。
        """
        agent_key = str(state.get("agent_key") or "")
        agent_modes = state.get("agent_chat_modes") or {}
        signals = self._derive_mode_signals(state)
        tools = ToolAvailability(
            has_kb=bool(state.get("project_ids")),
            has_web=bool(state.get("enable_websearch")),
            has_sandbox=False,
        )
        requested = str(state.get("requested_mode") or RequestedMode.AUTO.value)

        if agent_key == "builtin_fast":
            # 快速智能体: 固定 RAG 流程, 不升级、不开思考
            decision = ModeDecision(
                exec_mode=ExecMode.FAST,
                mode_reason="快速智能体: 固定 RAG 检索流程, 不开启思考",
                requested_mode=RequestedMode.FAST,
                config=self._mode_config_of(agent_key, "fast", agent_modes),
            )
        elif agent_key == "builtin_thinking":
            # 思考智能体: 有界 ReAct; 无工具时退化为仅检索+自答
            mode = ExecMode.DEEP if tools.can_deep else ExecMode.THINKING
            decision = ModeDecision(
                exec_mode=mode,
                mode_reason=(
                    "思考智能体: 有界 ReAct 多轮取证"
                    if tools.can_deep
                    else "思考智能体: 无可用工具, 退化为检索+自答"
                ),
                requested_mode=RequestedMode.THINKING,
                config=self._mode_config_of(agent_key, mode.value, agent_modes),
            )
        else:
            decision = resolve_mode(
                requested,
                signals,
                tools,
                config_of=lambda m: self._mode_config_of(agent_key, m, agent_modes),
            )
        logger.info(
            f"[Mode] agent={agent_key or '-'} requested={decision.requested_mode.value} "
            f"exec={decision.exec_mode.value} reason={decision.mode_reason}"
        )
        return {
            "requested_mode": decision.requested_mode.value,
            "exec_mode": decision.exec_mode.value,
            "mode_reason": decision.mode_reason,
            "mode_config": decision.config.model_dump(),
        }


    @staticmethod
    def _derive_mode_signals(state: RagChatState) -> ModeSignals:
        """从 state 派生意图信号(§2.2)

        - 意图分析给出的 complexity: complex=复合问题, cross_source=需跨源交叉
        - explicit_deep: 显式深度信号(意图强信号时置位)
        """
        signals: set[str] = set()
        info: RagHelpInfo | None = state.get("rag_help_info")
        complexity = str(getattr(info, "complexity", "") or "") if info else ""
        if complexity == "complex":
            signals.add(IntentSignal.COMPLEX.value)
        elif complexity == "cross_source":
            signals.add(IntentSignal.CROSS_SOURCE.value)
        if state.get("explicit_deep"):
            signals.add(IntentSignal.EXPLICIT_DEEP.value)
        return ModeSignals(signals=frozenset(signals))

    @staticmethod
    def _mode_config_of(agent_key: str, mode: str, agent_modes: dict | None = None):
        """取该智能体某档位的运行参数(智能体 chat_modes 为唯一来源, §2.1)

        优先级: 库中智能体 chat_modes(管理员在智能体设置中的调整) >
        代码内置 Manifest > 按档位回退内置智能体(旧客户端兼容)
        """
        if isinstance(agent_modes, dict) and isinstance(agent_modes.get(mode), dict):
            try:
                return ChatModeConfig.model_validate(agent_modes[mode])
            except Exception as exc:
                logger.warning(f"智能体 {agent_key} 的模式配置 {mode} 非法, 回退内置: {exc}")
        if agent_key in ("builtin_fast", "builtin_thinking"):
            config = resolve_mode_config(agent_key, mode)
            if config is not None:
                return config
        fallback = "builtin_fast" if mode == "fast" else "builtin_thinking"
        return resolve_mode_config(fallback, mode)

    # ──────────────────────────────────────────────
    # 深度取证(REQ-019 §3.3)
    # ──────────────────────────────────────────────

    async def _deep_agent_node(self, state: RagChatState) -> dict:
        """深度取证节点: 有界 ReAct 多轮取证 → 证据融合 → 写回 state

        循环本体与预算由通用执行器 AgentRunner 负责(业务无关), 本节点只负责
        业务编排: 拼取证提示词 → 调 DeepAgentRunner → 合并证据到 state。
        失败时降级为已有检索证据(不阻断回答)。
        """
        user_id: str = state["user_id"]
        llm = await self.user_model_service.get_llm_by_user_id(user_id)
        if llm is None:
            raise ValueError("无可用对话模型, 无法执行深度取证")

        info: RagHelpInfo | None = state.get("rag_help_info")
        query = info.vector_search if info and info.vector_search else ""
        # 取证阶段只需最近上下文, 避免历史过长挤占预算
        history = messages_trim_with_max_tokens(list(state["messages"]), max_tokens=4000)
        messages = [SystemMessage(content=DEEP_AGENT_SYSTEM_PROMPT)] + history

        try:
            result = await self._deep_runner.run(
                llm,
                user_id=user_id,
                project_ids=list(state.get("project_ids") or []),
                messages=messages,
                mode_config=state.get("mode_config") or {},
                enable_websearch=bool(state.get("enable_websearch")),
                conversation_id=state.get("conversation_id") or None,
                query=query,
                rerank_limit=int(state.get("rerank_limit", 20) or 20),
            )
        except Exception as e:
            logger.warning(f"深度取证失败, 降级为已有证据: {e}", exc_info=True)
            return {
                "deep_evidence": [],
                "deep_events": [],
                "deep_stop_reason": f"failed: {e}",
            }

        return {
            "deep_evidence": result.get("deep_evidence") or [],
            "deep_events": result.get("deep_events") or [],
            "deep_stop_reason": result.get("deep_stop_reason"),
            "knowledge_context_list": self._merge_knowledge(
                state.get("knowledge_context_list"), result.get("knowledge_context_list")
            ),
            "web_results": self._merge_web(
                state.get("web_results"), result.get("web_results")
            ),
            "skill_context": result.get("skill_context") or "",
        }

    @staticmethod
    def _merge_knowledge(base: Any, extra: Any) -> list:
        """合并基础检索片段与深度取证片段(按片段 ID 去重, 取证结果优先)"""
        merged: list = []
        seen: set[str] = set()
        for chunk in [*(extra or []), *(base or [])]:
            key = str(getattr(chunk, "id", "") or id(chunk))
            if key in seen:
                continue
            seen.add(key)
            merged.append(chunk)
        return merged

    @staticmethod
    def _merge_web(base: Any, extra: Any) -> list:
        """合并基础网络引用与深度取证引用(按 URL/标题去重, 取证结果优先)"""
        merged: list = []
        seen: set[str] = set()
        for item in [*(extra or []), *(base or [])]:
            key = str(getattr(item, "url", "") or getattr(item, "title", "") or id(item))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    async def _knowledge_search_node(self, state: RagChatState) -> dict:
        """知识库混合检索 + 可选联网搜索 + 合并 Rerank 精排

        - 未开启联网: 与原链路一致, 知识库粗排后按深度思考决定是否单独精排
        - 开启联网: 知识库只做粗排(候选更全), 网络结果与知识片段合并为统一候选集,
          由用户 Rerank 模型一次精排(top_n=rerank_limit), 按类型拆回两个结果列表
        - 联网失败静默降级(仅用知识库); 全部失败/零命中由路由节点决定是否进入知识缺口交互
        """
        rag_help_info: RagHelpInfo | None = state.get("rag_help_info")
        project_ids: list[str] = state.get("project_ids", [])
        user_id: str = state["user_id"]
        # 本轮消息附件: 已入库用户问答知识库(temp), 存在时必须定向召回(不依赖模型主动调用)
        attachment_names: list[str] = list(state.get("attachment_names") or [])
        temp_kb_id: str = (state.get("temp_kb_id") or "").strip()
        has_attachment = bool(attachment_names and temp_kb_id)
        # 精排开关跟随执行模式(模式即 Agent): fast 档不单独精排, thinking/deep 档精排
        exec_mode: str = state.get("exec_mode") or ""
        deep_thinking: bool = exec_mode in ("thinking", "deep")
        enable_websearch: bool = state.get("enable_websearch", False)
        # state 中获取前端传来的 rerank_limit，若无则给默认值 20
        rerank_limit: int = state.get("rerank_limit", 20)
        search_limit: int = state.get("search_limit", 50)
        # 不需要外部信息时跳过(显式清空联网状态, 防止 checkpointer 残留上一轮结果);
        # 带附件时强制检索问答知识库, 不能被意图分析的"无需外部信息"提前跳过
        if not (
            has_attachment
            or (project_ids and rag_help_info and rag_help_info.is_need_external_info)
        ):
            return {
                "knowledge_context_list": [],
                "web_results": [],
                "web_search_error": None,
                "search_error": None,
            }

        # 1. 知识库多路粗排: 向量路(语义 query) + 关键词路(全文 query)并行召回合并,
        #    (联网开启时粗排不做精排, 与网络结果合并后统一精排)
        # 检索重检次数由智能体 chat_modes.search_rounds 固定: 首轮零命中时换用
        # 全文/原始问题 query 重检, 达到上限即停止(快速智能体的固定 RAG 流程)
        mode_config: dict = state.get("mode_config") or {}
        try:
            search_rounds = max(1, int(mode_config.get("search_rounds", 1) or 1))
        except (TypeError, ValueError):
            search_rounds = 1
        query_candidates: list[str] = []
        if rag_help_info:
            for q in (
                rag_help_info.vector_search,
                rag_help_info.full_text_search,
                rag_help_info.intent,
            ):
                if q and q not in query_candidates:
                    query_candidates.append(q)
        if not query_candidates:
            # 意图分析缺失(附件场景强制检索)时以用户原问题兜底
            last = state["messages"][-1] if state.get("messages") else None
            query_candidates = [str(getattr(last, "content", "") or "")]

        # 1.0 附件定向召回: 先只在问答知识库内检索并置前, 避免被其它知识库片段挤占,
        #     保证"上传文件后提问"一定能发现附件内容(业界会话附件语料做法)
        attachment_chunks: list[ProjectDocumentChunkSearchResponse] = []
        if has_attachment:
            attachment_query = query_candidates[0]
            try:
                attachment_chunks = await self.project_document_chunk_service.search(
                    SearchRequest(
                        query_content=attachment_query,
                        keyword_query=attachment_query,
                        project_ids=[temp_kb_id],
                        limit=search_limit,
                        rerank_limit=rerank_limit,
                        enable_rerank=False,
                    ),
                    user_id,
                )
                logger.info(
                    f"[Search] 附件定向召回 | 文件={len(attachment_names)} "
                    f"片段={len(attachment_chunks)}"
                )
            except Exception as e:
                logger.warning(f"附件定向检索失败(继续常规检索): {e}")

        knowledge_context_list: list[ProjectDocumentChunkSearchResponse] = []
        search_error: str | None = None
        for idx, query_content in enumerate(query_candidates[:search_rounds]):
            request = SearchRequest(
                query_content=query_content,
                keyword_query=(
                    rag_help_info.full_text_search if rag_help_info and idx == 0
                    else query_content
                ),
                project_ids=project_ids,
                limit=search_limit,
                rerank_limit=rerank_limit,
                enable_rerank=deep_thinking and not enable_websearch,
            )
            try:
                knowledge_context_list = await self.project_document_chunk_service.search(
                    request, user_id
                )
            except Exception as e:
                # 检索失败(模型网络错误/无 embedding 模型等)与"确实无相关片段"语义不同,
                # 错误原因写入 state, 由 SEARCH 节点结束事件透传到前端过程区块
                logger.warning(f"知识库检索失败: {e}")
                search_error = str(e)
                break
            if knowledge_context_list:
                break

        # 附件片段置前 + 常规检索片段按 ID 去重追回(附件内容优先进入上下文)
        if attachment_chunks:
            seen_ids = {str(chunk.id) for chunk in attachment_chunks}
            knowledge_context_list = [
                *attachment_chunks,
                *(c for c in knowledge_context_list if str(c.id) not in seen_ids),
            ]

        # 2. 联网搜索(失败静默降级, 不阻断知识库链路); 使用意图分析产出的联网专用 query
        web_results: list[WebCitation] = []
        web_search_error: str | None = None
        if enable_websearch and rag_help_info:
            ws = await get_websearch_settings()
            try:
                response = await WebSearchService().search(
                    WSSearchRequest(
                        query=rag_help_info.web_search or rag_help_info.vector_search,
                        limit=ws.web_results_limit,
                    )
                )
                web_results = [
                    WebCitation(
                        title=item.title,
                        url=item.url,
                        source=item.source,
                        description=item.description,
                    )
                    for item in response.results
                ]
            except Exception as e:
                logger.warning(f"联网搜索失败(降级仅用知识库): {e}")
                web_search_error = str(e)

        # 3. 合并统一精排: 知识片段与网络引用同场竞争, 按相关性统一排序后拆回
        if enable_websearch and deep_thinking and (knowledge_context_list or web_results):
            rerank_llm = await self.user_model_service.get_llm_by_user_id(
                user_id, False, ModelType.RERANK
            )
            if rerank_llm:
                candidates: list = [*knowledge_context_list, *web_results]
                logger.info(
                    f"[Search] 联网合并精排 | 知识片段={len(knowledge_context_list)} "
                    f"网络结果={len(web_results)} top_n={rerank_limit}"
                )
                try:
                    merged = await self.project_document_chunk_service.rerank_candidates(
                        rerank_llm,
                        query_candidates[0],
                        candidates,
                        rerank_limit,
                    )
                    knowledge_context_list = [
                        item for item in merged
                        if isinstance(item, ProjectDocumentChunkSearchResponse)
                    ]
                    web_results = [item for item in merged if isinstance(item, WebCitation)]
                except Exception as e:
                    # 合并精排失败降级: 保留粗排顺序与原始网络顺序
                    logger.warning(f"联网合并精排失败, 降级返回粗排结果: {e}")
            else:
                logger.warning("[Search] 联网已开启但无可用 Rerank 模型, 跳过合并精排")

        return {
            "knowledge_context_list": knowledge_context_list,
            "search_error": search_error,
            "web_results": web_results,
            "web_search_error": web_search_error,
        }

    async def _clarify_interaction_node(self, state: RagChatState) -> dict:
        """澄清交互节点: 问题信息不足, 结束本次 run 请求用户补充(伪中断)

        下一条消息携带 interaction_response(kind=clarify) 后重新走意图分析并检索
        """
        info: RagHelpInfo | None = state.get("rag_help_info")
        question = (
            info.clarify_question
            if info and info.clarify_question
            else "为了更准确地回答您的问题，能否补充一些关键信息？"
        )
        spec = InteractionSpec(
            kind=InteractionKind.CLARIFY,
            title="需要补充信息",
            question=question,
            options=[],
            allow_text=True,
            text_placeholder="请输入补充信息（如具体的项目/实体/时间范围等）",
            context={"intent": info.intent if info else ""},
        )
        return {"pending_interaction": spec.model_dump(), "interaction_response": None}

    async def _knowledge_gap_node(self, state: RagChatState) -> dict:
        """知识缺口交互节点: 检索零命中, 邀请用户补充缺失内容或选择继续方式(伪中断)"""
        info: RagHelpInfo | None = state.get("rag_help_info")
        spec = InteractionSpec(
            kind=InteractionKind.KNOWLEDGE_GAP,
            title="知识库中未找到相关内容",
            question="知识库中未检索到与该问题匹配的内容，您希望如何继续？",
            options=[
                InteractionOption(
                    label="补充相关内容",
                    value="supplement",
                    description="粘贴您掌握的相关资料，回答将结合补充内容生成",
                ),
                InteractionOption(
                    label="直接用 AI 知识回答",
                    value="answer_directly",
                    description="跳过知识库，使用模型自身知识回答",
                ),
                InteractionOption(
                    label="换个问法重新检索",
                    value="rephrase",
                    description="调整问题表述后重新检索知识库",
                ),
            ],
            allow_text=True,
            text_placeholder="选择「补充相关内容」或「换个问法」后，在此输入资料/新问题",
            context={
                "query": info.vector_search if info else "",
                "project_ids": state.get("project_ids", []),
            },
        )
        return {"pending_interaction": spec.model_dump(), "interaction_response": None}

    async def _chat_node(self, state: RagChatState) -> dict:
        """LLM 对话节点: 拼接 system prompt + 历史消息 → 生成回复"""
        user_id: str = state["user_id"]
        llm = await self.user_model_service.get_llm_by_user_id(user_id)
        if llm is None:
            # 与 agent_chat 一致: 明确报错而非 AttributeError, 由 chat_stream 转 ERROR 事件
            raise ValueError("无可用对话模型, 请先在模型设置中绑定或由管理员配置默认公共模型")

        knowledge_context_list: list[ProjectDocumentChunkSearchResponse] = state.get(
            "knowledge_context_list", []
        )

        system_prompt = RAG_CHAT_SYSTEM_PROMPT
        if knowledge_context_list:
            knowledge_context = "\n".join(
                item.content
                for item in knowledge_context_list
                if getattr(item, "content", "")
            )
            system_prompt += RAG_CHAT_SYSTEM_PROMPT_TEMPLATE.format(
                knowledge_context=knowledge_context
            )
        # 联网检索引用注入(与知识库内容并列参考, 冲突时提示优先知识库)
        web_results: list[WebCitation] = state.get("web_results") or []
        if web_results:
            web_context = "\n".join(
                f"- {item.title}\n  摘要: {item.description}\n  来源: {item.source or item.url}"
                for item in web_results
                if item.title or item.description
            )
            if web_context:
                system_prompt += RAG_WEB_CONTEXT_TEMPLATE.format(web_context=web_context)
        # 用户补充的缺失内容(knowledge_gap 交互)作为额外参考注入
        supplement_content: str | None = state.get("supplement_content")
        if supplement_content:
            system_prompt += RAG_SUPPLEMENT_CONTEXT_TEMPLATE.format(
                supplement_content=supplement_content
            )
        # 技能产出单独注入(与检索证据区分, 模型知道它是技能产物, §3.3)
        skill_context: str | None = state.get("skill_context")
        if skill_context:
            system_prompt += RAG_SKILL_CONTEXT_TEMPLATE.format(
                skill_context=skill_context
            )

        # 按模型输入上限动态裁剪历史: 先扣除 system prompt 与输出预留, 再裁剪历史
        input_tokens = await self.user_model_service.get_chat_input_tokens(user_id)
        system_tokens = count_tokens(system_prompt)
        history_budget = max(512, input_tokens - system_tokens - 512)
        messages = messages_trim_with_max_tokens(
            list(state["messages"]), max_tokens=history_budget
        )
        # 用量元数据: 模型标识(思考模式包装前取) + 实际输入 token(system prompt + 裁剪后历史)
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None)
        # 思考档位跟随智能体配置: 快速智能体 off, 思考智能体默认开启(可配置)
        mode_config = state.get("mode_config") or {}
        llm = with_think_mode(llm, str(mode_config.get("think_level") or "off"))
        chat_messages = [SystemMessage(content=system_prompt)] + messages
        full_response = await llm.ainvoke(chat_messages)
        return {
            "messages": [full_response],
            "usage_meta": {
                "model_name": model_name,
                "prompt_tokens": messages_tokens(chat_messages),
            },
            # 清理交互状态: 本轮流交互闭环, 防止残留影响后续问题
            "pending_interaction": None,
            "interaction_response": None,
            "supplement_content": None,
        }

    # ──────────────────────────────────────────────
    # 交互响应处理
    # ──────────────────────────────────────────────

    async def _validate_interaction_response(
        self, config: RunnableConfig, interaction_response: dict | None
    ) -> dict | None:
        """校验交互响应与 checkpointer 中待响应请求匹配(防过期/伪造), 返回归一化响应"""
        if not isinstance(interaction_response, dict) or not interaction_response.get("interaction_id"):
            return None
        pending: dict | None = None
        try:
            snapshot = await self.chat_compiled_graph.aget_state(config)
            values = getattr(snapshot, "values", None)
            pending = values.get("pending_interaction") if isinstance(values, dict) else None
        except Exception as e:
            logger.warning(f"读取待响应交互状态失败: {e}")
        if not isinstance(pending, dict) or pending.get("interaction_id") != interaction_response.get("interaction_id"):
            logger.info(
                f"忽略过期/不匹配的交互响应: {interaction_response.get('interaction_id')}"
            )
            return None
        return {
            "interaction_id": pending.get("interaction_id"),
            "kind": str(pending.get("kind") or ""),
            "action": str(interaction_response.get("action") or "submit"),
            "value": str(interaction_response.get("value") or ""),
        }

    @staticmethod
    def _interaction_store_message(
        message: str, normalized_response: dict | None
    ) -> str:
        """交互响应用户消息的可读兜底(空输入时生成自然语言, 避免历史出现协议噪音)"""
        if message:
            return message
        if not normalized_response:
            return message
        kind = normalized_response.get("kind")
        action = normalized_response.get("action")
        value = normalized_response.get("value", "")
        if kind == InteractionKind.CLARIFY:
            if action == "skip":
                return "（跳过补充，请基于现有信息回答）"
            return value or "（补充信息）"
        if kind == InteractionKind.KNOWLEDGE_GAP:
            if action == "supplement":
                return value or "（补充内容）"
            if action == "answer_directly":
                return "（无需知识库，请直接用你的知识回答我的上一个问题）"
            if action == "rephrase":
                return value or "请基于知识库重新检索并回答我之前的问题"
        return value or f"（{kind} 响应: {action}）"


    # ──────────────────────────────────────────────
    # 流式聊天入口
    # ──────────────────────────────────────────────

    async def chat_stream(
        self,
        conversation_id: str,
        user_id: str,
        chat_request: ChatRequest,
    ) -> AsyncGenerator[StreamOne, None]:
        """
        流式聊天生成器，按事件类型 yield StreamOne:
        - STATUS:          阶段提示 (意图分析中 / 检索中)
        - AGENT_THINKING:  意图分析结果
        - MODE_DECISION:   执行模式决策结论(模式即 Agent, §2.2)
        - TOOL_CALL:       知识库检索结果(含结构化 data)
        - LLM_THINKING:    LLM reasoning tokens (若模型支持)
        - ANSWER:          正式回答 token
        - INTERACTION:     用户交互请求(澄清/知识缺口补充)
        - ERROR:           异常
        """
        raw_message = (chat_request.message or "").strip()
        interaction_response: dict | None = getattr(chat_request, "interaction_response", None)

        if not raw_message and not interaction_response:
            yield StreamOne(
                content="消息内容不能为空",
                stream_event_type=StreamEventType.ERROR,
            )
            return

        # 1. 校验交互响应(与待响应请求匹配才生效, 否则按普通消息处理)
        config: RunnableConfig = {"configurable": {"thread_id": conversation_id}}
        normalized_response = await self._validate_interaction_response(
            config, interaction_response
        )

        # 2. 持久化用户消息(交互响应空输入时用可读兜底文案)
        store_message = self._interaction_store_message(raw_message, normalized_response)
        # 附件: 已入库个人默认临时知识库, 用户消息 blocks 记附件标记(历史恢复附件芯片)
        attachments = (chat_request.attachments or [])[:TEMP_MAX_FILES]
        attachment_blocks: list[dict] | None = (
            [
                {
                    "node_name": "",
                    "stream_event_type": StreamEventType.TEMP_FILE.value,
                    "content": name,
                }
                for name in attachments
            ]
            or None
        )
        chat_message_user = ChatMessageCreate(
            conversation_id=conversation_id,
            role=RoleType.USER,
            content=store_message,
            blocks=attachment_blocks,
        )
        await self.chat_message_service.add(chat_message_user)

        # 3. 解析联网开关: 请求级显式覆盖优先, 未传(None)跟随通用配置全局默认
        enable_websearch = chat_request.enable_websearch
        if enable_websearch is None:
            enable_websearch = (await get_websearch_settings()).rag_enable

        # 检索范围自动并入用户临时知识库(存在时): 附件已入库, 检索即可命中;
        # kb_auto_only=用户未显式选择任何知识库(仅临时库并入), 检索零命中时
        # 降级直接回答(见 _route_after_search), 保持纯聊天不被知识缺口交互打断
        project_ids = list(chat_request.project_ids or [])
        # 知识库三态: auto=未勾选时自动匹配有权限的知识库 / manual=仅用勾选项 / off=禁用
        # (None=旧客户端行为: 空 project_ids 即本轮不检索知识库)
        kb_mode = (chat_request.kb_mode or "").strip().lower()
        if kb_mode not in ("auto", "manual", "off"):
            kb_mode = "manual"
        kb_auto_only = False
        if kb_mode == "off":
            project_ids = []
        elif kb_mode == "auto" and not project_ids:
            project_ids = await self._resolve_auto_projects(user_id)
            # 自动范围由后端解析, 用户并未显式指定: 零命中时直接回答而不打断追问
            kb_auto_only = True
        kb_auto_only = kb_auto_only or not project_ids
        # 问答知识库(会话附件入库)在非禁用态自动并入检索范围; 禁用态不检索任何知识库
        temp_kb = None if kb_mode == "off" else await get_temp_kb(user_id)
        if temp_kb and temp_kb.id not in project_ids:
            project_ids.append(temp_kb.id)

        run_messages: list[AnyMessage] = [HumanMessage(content=store_message)]

        # 4. 解析执行智能体(模式即 Agent): 问答页只提供两个内置智能体,
        #    执行方式与运行参数全部由 agent_id 决定; mode 仅作为旧客户端兼容
        agent_key = (chat_request.agent_id or "").strip()
        if not agent_key:
            try:
                conv = await self.conversation_service.get(conversation_id)
                agent_key = ((conv.agent_id if conv else "") or "").strip()
            except Exception as exc:
                logger.warning(f"读取会话智能体失败(按未选智能体处理): {exc}")
        # 智能体运行参数以库中配置为准(管理员可在智能体设置中调整)
        agent_modes: dict = {}
        if agent_key:
            try:
                from module_agent.service.agent import AgentService

                agent_row = await AgentService().agent_dao.get(agent_key)
                agent_modes = (agent_row.chat_modes if agent_row else None) or {}
            except Exception as exc:
                logger.warning(f"读取智能体运行参数失败(回退内置默认): {exc}")
        requested_mode = (chat_request.mode or "").strip().lower()
        if agent_key == "builtin_fast":
            requested_mode = RequestedMode.FAST.value
        elif agent_key == "builtin_thinking":
            requested_mode = RequestedMode.THINKING.value
        elif requested_mode not in (
            RequestedMode.AUTO.value,
            RequestedMode.FAST.value,
            RequestedMode.THINKING.value,
        ):
            requested_mode = RequestedMode.AUTO.value
        explicit_deep = False

        input_state: RagChatState = {
            "messages": run_messages,
            "project_ids": project_ids,
            "kb_auto_only": kb_auto_only,
            "temp_kb_id": temp_kb.id if temp_kb else "",
            "attachment_names": attachments,
            "user_id": user_id,
            "rerank_limit": getattr(chat_request, 'rerank_limit', 20), # 传递精排数量
            "enable_websearch": enable_websearch,
            # ── REQ-019 模式即 Agent ──
            "agent_key": agent_key,
            "agent_chat_modes": agent_modes,
            "requested_mode": requested_mode,
            "explicit_deep": explicit_deep,
            "conversation_id": conversation_id,
            # 模式决策结果每轮重算(先清空, 防 checkpointer 残留上一轮)
            "exec_mode": "",
            "mode_reason": "",
            "mode_config": None,
            "deep_evidence": [],
            "deep_events": [],
            "deep_stop_reason": None,
            "skill_context": None,
            # 联网状态先清空, SEARCH 节点按本轮结果覆写(防 checkpointer 残留上一轮)
            "web_results": None,
            "web_search_error": None,
            "interaction_response": normalized_response,
            "supplement_content": (
                normalized_response.get("value")
                if normalized_response
                and normalized_response.get("kind") == InteractionKind.KNOWLEDGE_GAP
                and normalized_response.get("action") == "supplement"
                else None
            ),
        }

        full_response = ""
        process_blocks: list[dict] = []
        resolved = None  # 模型解析结果(用量记账取 model_id; try 内赋值)
        try:
            # 兜底链可感知(v4 4.3): 绑定失效回退公共模型时, 先推送 STATUS 提示数据流向变化
            resolved = await self.user_model_service.resolve_model(
                user_id, ModelType.CHAT
            )
            if resolved.fallback_used and not resolved.binding_unset:
                # 绑定失效(被删/停用/无权)才提示数据流向变化; 未设置模型走默认公共模型属正常行为, 静默
                yield StreamOne(
                    content="绑定的对话模型不可用，已回退系统公共模型（数据将由公共模型处理，可在设置中调整）",
                    stream_event_type=StreamEventType.STATUS,
                )
            elif resolved.model_id is None:
                # 无可用模型(绑定失效/未绑定, 且无默认公共模型可回退): 直接报错, 不静默换模型
                yield StreamOne(
                    content="没有可用的对话模型(绑定失效且无默认公共模型可回退), 请在设置中绑定模型或联系管理员配置默认模型",
                    stream_event_type=StreamEventType.ERROR,
                )
                return
            async for event in self.chat_compiled_graph.astream_events(
                input_state, config=config, version="v2"
            ):
                for item in self._classifier.classify(event):
                    if item.stream_event_type == StreamEventType.ANSWER:
                        full_response += item.content
                    elif item.stream_event_type != StreamEventType.STATUS:
                        # 收集思考/检索等过程区块(跳过 status: 瞬态进度，由前端实时展示)
                        self._accumulate_process_block(process_blocks, item)

                    yield item

        except Exception as e:
            logger.error(f"流式聊天失败: {e}", exc_info=True)
            yield StreamOne(
                content=f"服务异常: {e}",
                stream_event_type=StreamEventType.ERROR,
            )
        finally:
            # 持久化助手消息(含过程区块，便于重新打开时恢复思考链路显示)
            # 客户端中止(停止生成)时生成器被 GeneratorExit 关闭, except Exception 捕获不到,
            # 必须放 finally 才能保证已生成的部分回答落库
            # 交互-only run(澄清/知识缺口, 无正文回答)也需落库: blocks 中含交互卡片供历史恢复
            if full_response or process_blocks:
                # 落库协程用 shield 脱离外层取消: 客户端断开时 sse-starlette 会取消流式任务,
                # finally 里直接 await 会被再次注入的 CancelledError 打断导致部分回答丢失
                persist_task = asyncio.create_task(
                    self.chat_message_service.add(
                        ChatMessageCreate(
                            conversation_id=conversation_id,
                            role=RoleType.ASSISTANT,
                            content=full_response,
                            blocks=process_blocks or None,
                        )
                    )
                )
                cancelled = False
                try:
                    await asyncio.shield(persist_task)
                except asyncio.CancelledError:
                    # 本任务被取消(客户端断开): 等落库协程完成后再传播取消
                    cancelled = True
                    try:
                        await persist_task
                    except Exception as e:
                        logger.error(f"助手消息持久化失败: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"助手消息持久化失败: {e}", exc_info=True)
                # 首次问答结束后自动生成会话标题(后台任务, 失败静默; 客户端中止也执行)
                # 交互响应的原文可能是空字符串(卡片点击提交), 用可读兜底文案生成标题
                if full_response:
                    asyncio.create_task(
                        maybe_auto_title(conversation_id, user_id, store_message, full_response)
                    )
                    # 旁路记录本轮问答用量(token + 成本快照, 失败不影响主流程;
                    # 后台任务执行, 客户端中止/取消也不受影响)
                    if resolved is not None:
                        asyncio.create_task(
                            self._record_usage(
                                config,
                                user_id,
                                conversation_id,
                                agent_key or None,
                                requested_mode,
                                resolved.model_id,
                                full_response,
                            )
                        )
                if cancelled:
                    raise

    async def _record_usage(
        self,
        config: RunnableConfig,
        user_id: str,
        conversation_id: str,
        agent_id: str | None,
        requested_mode: str,
        model_id: str | None,
        full_response: str,
    ) -> None:
        """旁路记录本轮问答用量(token + 成本快照); 任何异常只告警, 不影响主流程

        输入 token 取 chat 节点写入的 usage_meta(system prompt + 裁剪后历史),
        输出 token 按 full_response 估算, 模型标识/单价按 resolved.model_id 查库。
        """
        try:
            usage_meta: dict = {}
            exec_mode = ""
            try:
                snapshot = await self.chat_compiled_graph.aget_state(config)
                values = getattr(snapshot, "values", None) or {}
                usage_meta = values.get("usage_meta") or {}
                exec_mode = str(values.get("exec_mode") or "")
            except Exception as e:
                logger.warning(f"读取本轮用量元数据失败(按空口径记账): {e}")
            await ChatUsageService().record(
                user_id=user_id,
                conversation_id=conversation_id,
                prompt_tokens=int(usage_meta.get("prompt_tokens") or 0),
                completion_tokens=count_tokens(full_response) if full_response else 0,
                agent_id=agent_id or None,
                model_id=model_id,
                model_name=usage_meta.get("model_name"),
                mode=exec_mode or requested_mode,
            )
        except Exception as e:
            logger.warning(f"记录问答用量失败 conversation={conversation_id}: {e}")

    @staticmethod
    def _accumulate_process_block(blocks: list[dict], item: StreamOne) -> None:
        """按 (事件类型, 节点名) 累积过程区块(供前端折叠区恢复显示)

        data(结构化检索结果/交互请求等)随首条事件写入, 同类合并时补写缺失键;
        按节点名细分, 使检索与深度取证等同类事件分属不同区块
        """
        evt = item.stream_event_type.value
        node = item.node_name
        for b in blocks:
            if b.get("stream_event_type") == evt and b.get("node_name") == node:
                b["content"] += item.content
                if item.data is not None and "data" not in b:
                    b["data"] = item.data
                return
        blocks.append(
            {
                "node_name": item.node_name,
                "stream_event_type": evt,
                "content": item.content,
                **({"data": item.data} if item.data is not None else {}),
            }
        )

    # ──────────────────────────────────────────────
    # Summary Graph
    # ──────────────────────────────────────────────

    def _build_summary_graph(self) -> StateGraph:
        """构建对话总结 graph"""
        graph = StateGraph(SummaryState)
        graph.add_node(GraphNode.SUMMARY, self._summarize_node)
        graph.add_edge(START, GraphNode.SUMMARY)
        graph.add_edge(GraphNode.SUMMARY, END)
        return graph

    async def _summarize_node(self, state: SummaryState) -> dict:
        """LLM 结构化总结: 生成标题 + 摘要"""
        user_id = state["user_id"]
        llm = await self.user_model_service.get_llm_by_user_id(user_id, streaming=False)
        if llm is None:
            logger.warning(f"用户 {user_id} 无可用对话模型, 总结降级返回默认摘要")
            return {"summary": ConversationSummary()}
        structured_llm = llm.with_structured_output(ConversationSummary)

        messages: list[AnyMessage] = [
            SystemMessage(content=SUMMARIZE_SYSTEM_PROMPT)
        ] + list(state["messages"])

        try:
            result: ConversationSummary = await structured_llm.ainvoke(messages)
        except Exception as e:
            logger.warning(f"LLM 结构化总结失败: {e}")
            result = ConversationSummary()
        return {"summary": result}

    async def summarize_conversation(
        self, conversation_id: str, user_id: str
    ) -> ConversationSummary:
        """总结对话并持久化标题"""
        try:
            config: RunnableConfig = {"configurable": {"thread_id": conversation_id}}
            result = await self.summary_compiled_graph.ainvoke(
                SummaryState(user_id=user_id), config=config
            )
            summary: ConversationSummary = (
                result.get("summary") or ConversationSummary()
            )
            # 仅在生成出有效标题时更新, 避免 LLM 失败/空标题覆盖原对话标题
            if summary.title:
                await self.conversation_service.update(
                    conversation_id, ConversationUpdate(title=summary.title)
                )
            return summary
        except Exception as e:
            logger.error(f"总结对话失败: {e}", exc_info=True)
            return ConversationSummary()
