"""智能体执行循环(REQ-013): 手工 tool-calling 流式对话

不引入 langgraph: 手工循环 `llm.bind_tools → astream 累积 → 执行工具 → 回填 → 再生成`,
历史从 chat_message 表重建(不用 checkpointer, 与 rag 图管线彻底隔离零冲突)。

事件流复用 module_rag 的 StreamOne/StreamEventType, 经 agui_event_generator 输出
AG-UI 协议, 前端聚合逻辑与 rag 会话完全一致。
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_ai.utils.llm.types import ModelType, RoleType
from module_agent.dao.agent import AgentDao
from module_agent.do.agent import Agent
from module_agent.service.agent import DEFAULT_AGENT_PROMPT, DEFAULT_CHAT_PROMPT
from module_agent.skills.registry import SKILLS, SkillContext
from module_rag.do.chat_message import ChatMessageCreate
from module_rag.do.rag_chat import StreamEventType, StreamOne
from module_rag.service.chat_message import ChatMessageService
from module_rag.service.conversation import ConversationService
from module_rag.service.user_model import UserModelService

logger = logging.getLogger(__name__)

# 防失控: 单轮问答内最大 LLM 调用轮数(含工具执行轮)
MAX_TOOL_ROUNDS = 8
# 重建历史时携带的最大消息条数(用户+助手)
HISTORY_MAX_MESSAGES = 20
# 工具结果回填 ToolMessage 的字符上限(超出截断, 防上下文膨胀)
TOOL_RESULT_MAX_CHARS = 6000
# 过程区块中工具结果的展示上限
TOOL_DISPLAY_MAX_CHARS = 2000


class AgentChatRequest(BaseModel):
    """智能体对话请求"""

    message: str = Field(..., min_length=1, description="用户消息")
    agent_id: str = Field(default="", description="智能体ID(空则用会话绑定的)")


class AgentRunnerService:
    """智能体执行循环服务(无状态, 每次运行即时构建工具与上下文)"""

    def __init__(
        self,
        agent_dao: AgentDao | None = None,
        chat_message_service: ChatMessageService | None = None,
        conversation_service: ConversationService | None = None,
        user_model_service: UserModelService | None = None,
    ):
        """依赖注入构造器"""
        self.agent_dao = agent_dao or AgentDao()
        self.chat_message_service = chat_message_service or ChatMessageService()
        self.conversation_service = conversation_service or ConversationService()
        self.user_model_service = user_model_service or UserModelService()

    # ── 工具构建 ──

    @staticmethod
    def _build_tool(skill_name: str, ctx: SkillContext) -> BaseTool:
        """按技能定义与运行上下文构建 LangChain 工具(closure 捕获, 无全局态)"""
        skill = SKILLS[skill_name]

        async def _run(**kwargs: Any) -> str:
            args = skill.args_model(**kwargs)
            return await skill.func(args, ctx)

        return StructuredTool.from_function(
            coroutine=_run,
            name=skill.name,
            description=skill.description,
            args_schema=skill.args_model,
        )

    # ── 历史重建 ──

    async def _load_history(self, conversation_id: str) -> list:
        """从 chat_message 表重建最近 N 条历史(user→Human / assistant→AI)

        显式传分页: service 无参路径内部构造 size=1000 超上限会 ValidationError(预存缺陷)
        """
        from common.utils.db.schema.pagination import PaginationParams

        page = await self.chat_message_service.list_by_conversation(
            conversation_id, PaginationParams(page=1, size=200)
        )
        history = []
        for msg in page.items[-HISTORY_MAX_MESSAGES:]:
            if msg.role == RoleType.USER:
                history.append(HumanMessage(content=msg.content))
            else:
                history.append(AIMessage(content=msg.content))
        return history

    # ── 执行循环 ──

    async def chat_stream(
        self,
        conversation_id: str,
        user_id: str,
        agent_id: str,
        request: AgentChatRequest,
    ) -> AsyncGenerator[StreamOne, None]:
        """智能体流式对话主循环(事件语义与 rag chat_stream 一致)"""
        try:
            agent = await self._resolve_agent(conversation_id, user_id, agent_id)
        except (NotFoundError, BusinessError) as e:
            yield StreamOne(content=str(e), stream_event_type=StreamEventType.ERROR)
            return

        raw_message = (request.message or "").strip()
        if not raw_message:
            yield StreamOne(content="消息内容不能为空", stream_event_type=StreamEventType.ERROR)
            return

        # 用户消息落库
        await self.chat_message_service.add(
            ChatMessageCreate(
                conversation_id=conversation_id,
                role=RoleType.USER,
                content=raw_message,
            )
        )

        # 模型解析(绑定失效回退提示与 rag 行为一致)
        resolved = await self.user_model_service.resolve_model(user_id, ModelType.CHAT)
        if resolved.fallback_used and not resolved.binding_unset:
            yield StreamOne(
                content="绑定的对话模型不可用，已回退系统公共模型（数据将由公共模型处理，可在设置中调整）",
                stream_event_type=StreamEventType.STATUS,
            )
        elif resolved.model_id is None:
            yield StreamOne(
                content="没有可用的对话模型(绑定失效且无默认公共模型可回退), 请在设置中绑定模型或联系管理员配置默认模型",
                stream_event_type=StreamEventType.ERROR,
            )
            return
        llm = await self.user_model_service.get_llm_by_user_id(user_id)

        # 系统提示: 自定义优先, 空则按是否挂技能回退内置默认
        prompt = (agent.default_prompt or "").strip()
        if not prompt:
            prompt = DEFAULT_AGENT_PROMPT if agent.skills else DEFAULT_CHAT_PROMPT
        skill_ctx = SkillContext(
            user_id=user_id, default_project_ids=agent.default_project_ids or []
        )
        tools = [
            self._build_tool(name, skill_ctx)
            for name in agent.skills
            if name in SKILLS
        ]

        history = await self._load_history(conversation_id)
        # 本轮消息列表: 系统提示 + 历史 + 当前问题(工具调用轮在尾部追加)
        messages: list = [SystemMessage(content=prompt), *history, HumanMessage(content=raw_message)]

        full_response = ""
        process_blocks: list[dict] = []
        try:
            async for item in self._run_loop(llm, messages, tools, skill_ctx):
                if item.stream_event_type == StreamEventType.ANSWER:
                    full_response += item.content
                elif item.stream_event_type != StreamEventType.STATUS:
                    self._accumulate(process_blocks, item)
                yield item
        except Exception as e:
            logger.error(f"智能体对话失败: {e}", exc_info=True)
            yield StreamOne(
                content=f"服务异常: {e}", stream_event_type=StreamEventType.ERROR
            )
        finally:
            await self._persist_assistant_message(
                conversation_id, user_id, raw_message, full_response, process_blocks
            )

    # ── 内部: agent 解析与会话归属校验 ──

    async def _resolve_agent(
        self, conversation_id: str, user_id: str, agent_id: str
    ) -> Agent:
        """会话归属校验 + Agent 可见性校验(公开或本人创建)"""
        conversation = await self.conversation_service.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise NotFoundError("会话不存在或无权访问")
        real_id = agent_id or conversation.agent_id or ""
        if not real_id:
            raise BusinessError("该会话未绑定智能体, 请指定 agent_id")
        agent = await self.agent_dao.get(real_id)
        if agent is None or not (
            agent.is_public or agent.owner_user_id == user_id
        ):
            raise NotFoundError(f"未找到ID为 {real_id} 的智能体")
        return agent

    # ── 内部: 工具调用循环 ──

    async def _run_loop(
        self, llm, messages: list, tools: list, ctx: SkillContext
    ) -> AsyncGenerator[StreamOne, None]:
        """LLM 循环: 流式生成 → 有工具调用则执行回填再生成, 无则结束"""
        for round_no in range(MAX_TOOL_ROUNDS):
            # 最后一轮强制不挂工具, 确保输出最终答案而非再次调用
            last_round = round_no == MAX_TOOL_ROUNDS - 1
            runnable = llm.bind_tools(tools) if tools and not last_round else llm

            if tools and round_no == 0:
                yield StreamOne(
                    content="正在思考…", stream_event_type=StreamEventType.STATUS
                )
            if last_round and tools:
                yield StreamOne(
                    content="已达工具调用轮数上限, 本轮不再调用工具, 直接生成最终回答",
                    stream_event_type=StreamEventType.STATUS,
                )

            final: AIMessageChunk | None = None
            async for chunk in runnable.astream(messages):
                if final is None:
                    final = chunk
                else:
                    final = final + chunk
                # 推理流(模型支持时)
                for token in self._reasoning_text(chunk):
                    yield StreamOne(
                        content=token,
                        stream_event_type=StreamEventType.LLM_THINKING,
                    )
                # 正文流
                content = self._content_text(chunk)
                if content:
                    yield StreamOne(content=content, stream_event_type=StreamEventType.ANSWER)

            if final is None:
                yield StreamOne(
                    content="模型未返回内容", stream_event_type=StreamEventType.ERROR
                )
                return

            messages.append(final)
            tool_calls = getattr(final, "tool_calls", None) or []
            if not tool_calls:
                return  # 无工具调用: 答案已流式输出完毕

            # 逐个执行工具并回填
            for tc in tool_calls:
                name = tc.get("name", "") or ""
                args = tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                skill = SKILLS.get(name)
                display = skill.display_name if skill else name
                args_brief = json.dumps(args, ensure_ascii=False)[:300]
                yield StreamOne(
                    content=f"调用工具 {display}: {args_brief}",
                    stream_event_type=StreamEventType.TOOL_CALL,
                    data={
                        "tool_name": name,
                        "display_name": display,
                        "arguments": args,
                        "capability": skill.capability.value if skill else "read",
                    },
                )
                try:
                    if skill is None:
                        raise ValueError(f"未注册的技能: {name}")
                    validated = skill.args_model(**args)
                    result = await skill.func(validated, ctx)
                except Exception as e:  # 工具失败降级为错误文本, 循环继续
                    logger.warning(f"技能 {name} 执行失败: {e}")
                    result = f"工具执行失败: {e}"
                display_result = result[:TOOL_DISPLAY_MAX_CHARS] + (
                    "…" if len(result) > TOOL_DISPLAY_MAX_CHARS else ""
                )
                yield StreamOne(
                    content=display_result,
                    stream_event_type=StreamEventType.TOOL_CALL,
                )
                messages.append(
                    ToolMessage(
                        content=result[:TOOL_RESULT_MAX_CHARS],
                        tool_call_id=tc.get("id", "") or name,
                    )
                )

    # ── 内部: 消息抽取(与 rag StreamEventClassifier 同口径) ──

    @staticmethod
    def _content_text(chunk: object) -> str:
        """读取回答内容(纯文本 chunk 为主)"""
        content = getattr(chunk, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        return ""

    @staticmethod
    def _reasoning_text(chunk: object) -> list[str]:
        """读取推理内容(chunk 属性或 additional_kwargs)"""
        reasoning = getattr(chunk, "reasoning_content", None)
        if not reasoning:
            additional = getattr(chunk, "additional_kwargs", None) or {}
            reasoning = additional.get("reasoning_content")
        return [reasoning] if isinstance(reasoning, str) and reasoning else []

    # ── 内部: 过程区块与持久化(口径同 rag chat_stream) ──

    @staticmethod
    def _accumulate(blocks: list[dict], item: StreamOne) -> None:
        """按 stream_event_type 累积过程区块(供前端折叠区恢复)"""
        evt = item.stream_event_type.value
        for b in blocks:
            if b.get("stream_event_type") == evt:
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

    async def _persist_assistant_message(
        self,
        conversation_id: str,
        user_id: str,
        user_message: str,
        full_response: str,
        process_blocks: list[dict],
    ) -> None:
        """助手消息落库 + 首轮自动标题(shield 防客户端断开丢失, 口径同 rag)"""
        from module_rag.service.conversation_title import maybe_auto_title

        if not (full_response or process_blocks):
            return
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
            cancelled = True
            try:
                await persist_task
            except Exception as e:
                logger.error(f"助手消息持久化失败: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"助手消息持久化失败: {e}", exc_info=True)
        else:
            if full_response:
                asyncio.create_task(
                    maybe_auto_title(conversation_id, user_id, user_message, full_response)
                )
        if cancelled:
            raise
