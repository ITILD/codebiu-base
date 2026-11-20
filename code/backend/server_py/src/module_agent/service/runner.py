"""智能体执行循环(REQ-013): 手工 tool-calling 流式对话

不引入 langgraph: 手工循环 `llm.bind_tools → astream 累积 → 执行工具 → 回填 → 再生成`,
历史从 chat_message 表重建(不用 checkpointer, 与 rag 图管线彻底隔离零冲突)。

事件流复用 module_rag 的 StreamOne/StreamEventType, 经 agui_event_generator 输出
AG-UI 协议, 前端聚合逻辑与 rag 会话完全一致。
"""

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator
from uuid import uuid4

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_ai.utils.llm.types import ModelType, RoleType
from module_agent.dao.agent import AgentDao
from module_agent.dao.plan import AgentPlanEventDao, AgentPlanItemDao
from module_agent.do.agent import Agent
from module_agent.do.agent_plan import AgentPlanEvent, AgentPlanItem
from module_agent.service.agent import DEFAULT_AGENT_PROMPT, DEFAULT_CHAT_PROMPT
from module_agent.service.skill_runtime import SkillContext
from module_agent.skills.manifest import tool_name_to_uid
from module_agent.skills.registry import get_skill
from module_rag.do.chat_message import ChatMessageCreate
from module_rag.do.rag_chat import StreamEventType, StreamOne
from module_rag.service.chat_message import ChatMessageService
from module_rag.service.conversation import ConversationService
from module_rag.service.user_model import UserModelService

if TYPE_CHECKING:  # 仅类型检查用(避免运行时循环导入)
    from module_agent.skills.adapter import ToolRegistration

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
    async def _build_tools(agent: Agent, ctx: SkillContext) -> ToolRegistration:
        """按 agent 勾选的技能经 ToolGate 条件注册(与 rag 深度路径同规则, REQ-019 §5.1)

        - 能力: 所需能力不可解析的技能不注册(模型看不到不可用的工具);
        - 特性: agent 显式勾选联网/沙箱类技能即视为会话级授权;
          知识库特性按 agent.default_project_ids 授权范围判定;
        - 熔断: 会话级 SkillCircuitBreaker(连续失败自动摘除);
        - skills=[] 为明确无技能(传 [], 与 None=全量区分)
        """
        from module_agent.skills.adapter import (
            FEATURE_KNOWLEDGE_BASE,
            FEATURE_SANDBOX,
            FEATURE_WEB,
            SkillCircuitBreaker,
            ToolGate,
            build_gated_tools,
            get_skill,
            list_manifests,
        )

        if agent.skills is None:
            manifests = list_manifests(agent_callable_only=True)
        else:
            manifests = []
            for key in agent.skills:
                manifest = get_skill(key)
                if manifest is None or not manifest.agent_callable:
                    continue
                manifests.append(manifest)

        # 能力解析(所需键聚合后一次解析, 口径与 deep_agent 一致)
        capability_keys: set[str] = set()
        for manifest in manifests:
            capability_keys.update(manifest.required_capabilities)
        available: set[str] = set()
        if capability_keys:
            from module_ai.service.capability_registry import resolve as resolve_capability

            for key in capability_keys:
                try:
                    resolved = await resolve_capability(key, ctx.user_id)
                except Exception:  # 能力解析失败按不可用处理(不注册, 不阻塞对话)
                    continue
                if resolved.available:
                    available.add(key)

        # 特性授权: 显式勾选视为授权; 知识库按项目范围
        features: set[str] = set()
        if ctx.project_ids:
            features.add(FEATURE_KNOWLEDGE_BASE)
        for manifest in manifests:
            if FEATURE_WEB in manifest.requires_features:
                features.add(FEATURE_WEB)
            if FEATURE_SANDBOX in manifest.requires_features:
                features.add(FEATURE_SANDBOX)

        return await build_gated_tools(
            [m.uid for m in manifests],
            ctx,
            ToolGate(features=features, available_capabilities=available, project_ids=list(ctx.project_ids)),
            breaker=SkillCircuitBreaker(),
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
            user_id=user_id,
            project_ids=agent.default_project_ids or [],
            conversation_id=conversation_id,
            entry="agent",
        )
        # skills=[] 表示明确不挂载任何工具(与 None=全量区分);
        # 门控(能力/特性/熔断)未通过的技能不注册, 并以 STATUS 告知用户原因
        registration = await self._build_tools(agent, skill_ctx)
        tools = registration.tools
        if registration.skipped:
            brief = "; ".join(f"{s['key']}({s['reason']})" for s in registration.skipped)
            yield StreamOne(
                content=f"部分技能本次不可用已跳过: {brief}",
                stream_event_type=StreamEventType.STATUS,
            )
        history = await self._load_history(conversation_id)
        # 本轮消息列表: 系统提示 + 历史 + 当前问题(工具调用轮在尾部追加)
        messages: list = [SystemMessage(content=prompt), *history, HumanMessage(content=raw_message)]

        full_response = ""
        process_blocks: list[dict] = []
        try:
            # 五拍协议(REQ-019 批次 5): 任务型 ai_agent(execution_strategy=plan_execute)
            # 走「一条清单、一个循环、一道闸门」, 完成由验收判定, 不走自由对话循环;
            # 业务工具按 §5.1 条件注册后传入(与 chat 分支同一 build 结果)
            if (agent.execution_strategy or "") == "plan_execute":
                async for item in self._run_plan_execute(
                    llm, agent, conversation_id, user_id, raw_message, tools, skill_ctx
                ):
                    if item.stream_event_type == StreamEventType.ANSWER:
                        full_response += item.content
                    elif item.stream_event_type != StreamEventType.STATUS:
                        self._accumulate(process_blocks, item)
                    yield item
                return
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

    # ── 内部: 五拍协议(任务型 ai_agent, REQ-019 批次 5) ──

    async def _run_plan_execute(
        self, llm, agent: Agent, conversation_id: str, user_id: str,
        goal: str, tools: list[BaseTool], ctx: SkillContext,
    ) -> AsyncGenerator[StreamOne, None]:
        """五拍协议执行: 清单(write_plan) → 执行 → 交卷(submit) → 验收 → 改单

        - write_plan/submit 是运行时控制动词, 不进 Skill 注册表(设计 §4.3);
        - 业务工具按 §5.1 条件注册(复用 chat 分支同一 build 结果)传入执行阶段;
        - 事件经 asyncio.Queue 桥接为实时流(非 run 结束后回放);
        - 清单投影随状态变化事件实时 upsert(§4.8: 投影=日志的单向投影);
        - skill_invocation.agent_run_id 关联本次运行(§7), 触顶回填 mode_budget_hit;
        - 北极星三项由 verdict_* 字段与 usage 统计(§4.9)。
        """
        from module_agent.service.agent_planner import PlanBudget, PlanExecutor

        item_dao = AgentPlanItemDao()
        event_dao = AgentPlanEventDao()
        run_id = uuid4().hex
        ctx.run_id = run_id  # 本次运行的技能调用落 skill_invocation.agent_run_id(§7)
        queue: asyncio.Queue[StreamOne | None] = asyncio.Queue()

        async def on_event(event_type: str, item_id: str, payload: dict) -> None:
            """事件落库(系统事实源) + 实时投影 + 实时下发; 失败不影响执行"""
            payload.setdefault("run_id", run_id)  # 断线兜底: 前端凭 run_id 拉清单投影
            snapshot = payload.get("items") or []
            try:
                await event_dao.add(AgentPlanEvent(
                    run_id=payload.get("run_id") or run_id,
                    event_type=event_type,
                    item_id=item_id or "",
                    payload={k: v for k, v in payload.items()
                             if k not in ("run_id", "conversation_id", "items")},
                    conversation_id=conversation_id,
                    user_id=user_id,
                ))
            except Exception as e:
                logger.warning(f"agent_plan_event 落库失败: {e}")
            for it in snapshot:  # 投影=日志单向投影(§4.8), 随状态变化事件实时 upsert
                try:
                    await item_dao.upsert(AgentPlanItem(
                        run_id=run_id, item_id=it["id"], goal=it["goal"],
                        acceptance_kind=it["acceptance_kind"],
                        acceptance_spec=it["acceptance_spec"],
                        acceptance_hash=it.get("acceptance_hash") or "",
                        status=it["status"], attempts=it.get("attempts") or 0,
                        last_reason=it.get("last_reason") or "",
                        verdict_passed=it.get("verdict_passed"),
                        verdict_reason=it.get("verdict_reason") or "",
                        conversation_id=conversation_id, user_id=user_id,
                    ))
                except Exception as e:
                    logger.warning(f"agent_plan_item 投影失败: {e}")
            await queue.put(self._plan_event_stream(event_type, item_id, payload))

        # 工作区: cmd/artifact 验收的取证目录(每次运行独立)
        workspace = tempfile.mkdtemp(prefix="agent_plan_")
        # 预算: chat_modes["plan_execute"] 可覆盖(内置/自定义 Agent 的模式配置同源)
        overrides = ((agent.chat_modes or {}).get("plan_execute") or {})
        budget_keys = {"max_model_calls", "max_tool_calls", "wall_clock_s", "tool_timeout_s"}
        budget = PlanBudget(**{k: int(v) for k, v in overrides.items() if k in budget_keys})

        yield StreamOne(
            content="已进入任务执行模式(五拍协议): 先分解清单, 完成由验收判定",
            stream_event_type=StreamEventType.STATUS,
        )
        executor = PlanExecutor(on_event=on_event)
        run_task = asyncio.create_task(executor.run(
            goal, llm, list(tools), workspace, budget,
            run_id=run_id, conversation_id=conversation_id,
        ))
        # 队列桥接: on_event 产出实时下发, run 结束后先排空队列再取结果
        get_task: asyncio.Task | None = None
        try:
            while True:
                if get_task is None:
                    if run_task.done() and queue.empty():
                        break
                    get_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {run_task, get_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if get_task in done:
                    item = get_task.result()
                    get_task = None
                    if item is not None:
                        yield item
                elif get_task is not None:
                    get_task.cancel()  # 运行已先结束且队列已空, 收掉取数任务
                    get_task = None
                    if run_task.done():
                        break
        finally:
            if get_task is not None and not get_task.done():
                get_task.cancel()
            if not run_task.done():
                # 客户端断开 = 外部取消(§4.6 守卫三); 正常完成路径不会走到这里
                run_task.cancel()
                run_task.add_done_callback(
                    lambda t: t.exception() if not t.cancelled() else None
                )

        try:
            result = await run_task
        except Exception as e:
            logger.error(f"五拍协议执行失败: {e}", exc_info=True)
            yield StreamOne(content=f"任务执行异常: {e}", stream_event_type=StreamEventType.ERROR)
            return

        # 预算触顶回填标记(§7 mode_budget_hit, 北极星恶化时下钻用)
        if result.stop_reason == "budget":
            try:
                await self._mark_budget_hit(run_id)
            except Exception as e:
                logger.warning(f"mode_budget_hit 回填失败: {e}")

        usage = result.usage or {}
        # run 收尾事件(REQ-002 §7.1 北极星看板数据源): usage 仅存内存, 必须落事件日志;
        # 清单快照随事件一并投影, 保证终态与验收事实入库(§4.8 单向投影)
        try:
            await on_event(
                "run_finished",
                "",
                {
                    "run_id": run_id,
                    "agent_key": agent.key,
                    "stop_reason": result.stop_reason,
                    "status": result.status,
                    "usage": usage,
                    "item_total": len(result.items),
                    "item_passed": sum(
                        1 for i in result.items if i.verdict_passed is True
                    ),
                    "items": [PlanExecutor._item_snapshot(i) for i in result.items],
                },
            )
        except Exception as e:
            logger.warning(f"run_finished 事件落库失败: {e}")

        # 最终报告(流式输出, 北极星可见)
        stop_text = {
            "completed": "全部任务通过验收",
            "budget": "预算触顶, 已优雅收尾",
            "repeat_action": "检测到重复动作, 已停止",
            "replan_budget": "改单次数达上限, 已停止",
            "no_plan": "未能生成任务清单",
        }.get(result.stop_reason, result.stop_reason)
        perf = (f"(模型调用 {usage.get('model_calls', 0)} 次 / 工具 {usage.get('tool_calls', 0)} 次"
                f" / 耗时 {usage.get('elapsed_ms', 0) / 1000:.1f}s)")
        lines = [f"任务执行报告: {result.summary}({stop_text}) {perf}"]
        for item in result.items:
            mark = "✓" if item.verdict_passed else ("✗" if item.verdict_passed is False else "-")
            lines.append(f"{mark} {item.id} {item.goal} [{item.acceptance.render()}]"
                         + (f" 尝试{item.attempts}次" if item.attempts else ""))
        yield StreamOne(content="\n".join(l for l in lines if l),
                        stream_event_type=StreamEventType.ANSWER)

    @staticmethod
    def _plan_event_stream(event_type: str, item_id: str, payload: dict) -> StreamOne | None:
        """五拍协议事件 → 前端可见事件(§8: agent.plan_update / agent.verdict CUSTOM 事件)

        submit/experience 随裁决与最终报告呈现, 不重复下发(返回 None 跳过)
        """
        if event_type == "write_plan":
            return StreamOne(
                content=f"任务清单已更新({payload.get('count', '?')} 项): {payload.get('reason', '')}",
                stream_event_type=StreamEventType.TOOL_CALL,
                data={"event_type": "agent.plan_update", "plan_count": payload.get("count"),
                      "items": payload.get("items"), "run_id": payload.get("run_id", "")},
            )
        if event_type == "verdict":
            mark = "验收通过" if payload.get("passed") else "验收未通过"
            return StreamOne(
                content=f"{item_id} {mark}: {payload.get('reason', '')}",
                stream_event_type=StreamEventType.TOOL_CALL,
                data={"event_type": "agent.verdict", "passed": payload.get("passed"),
                      "item_id": item_id, "reason": payload.get("reason", ""),
                      "attempts": payload.get("attempts", 0),
                      "run_id": payload.get("run_id", "")},
            )
        if event_type == "revise":
            return StreamOne(
                content=f"清单已修订(失败项 {item_id} 两败改单)",
                stream_event_type=StreamEventType.STATUS,
            )
        if event_type == "write_plan_rejected":
            errors = "; ".join(payload.get("errors") or [])
            return StreamOne(
                content=f"清单被拒绝: {errors[:300]}",
                stream_event_type=StreamEventType.STATUS,
            )
        if event_type == "guard_stop":
            return StreamOne(
                content=f"运行被守卫停止: {payload.get('reason')}",
                stream_event_type=StreamEventType.STATUS,
            )
        return None

    @staticmethod
    async def _mark_budget_hit(run_id: str) -> None:
        """该运行触顶后, 关联的 skill_invocation 打预算命中标记(§7)"""
        from sqlalchemy import update

        from common.config.db import db_manager
        from module_agent.do.skill import SkillInvocation

        async with db_manager.db_rel.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(SkillInvocation)
                    .where(SkillInvocation.agent_run_id == run_id)
                    .values(mode_budget_hit=True)
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
        answer_emitted = False  # 是否流式输出过正文(空响应兜底提示用)
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
                    answer_emitted = True
                    yield StreamOne(content=content, stream_event_type=StreamEventType.ANSWER)

            if final is None:
                yield StreamOne(
                    content="模型未返回内容", stream_event_type=StreamEventType.ERROR
                )
                return

            messages.append(final)
            tool_calls = getattr(final, "tool_calls", None) or []
            if not tool_calls:
                # 无工具调用: 答案已流式输出完毕; 若整轮未吐任何正文
                # (如推理模型被截断在思考阶段), 显式提示而非静默结束
                if not answer_emitted:
                    yield StreamOne(
                        content="模型未返回正文内容(响应为空或被截断), 请重试或更换模型/模式",
                        stream_event_type=StreamEventType.ERROR,
                    )
                return

            # 逐个执行工具并回填(REQ-018: 工具经 Tool Adapter 闭包 → SkillRuntime)
            for tc in tool_calls:
                name = tc.get("name", "") or ""
                args = tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_obj = next((t for t in tools if t.name == name), None)
                # 展示信息从工具 metadata 直取 Manifest(多级命名空间免反解析)
                manifest = getattr(tool_obj, "metadata", None) or {}
                manifest = manifest.get("skill_manifest") if isinstance(manifest, dict) else None
                if manifest is None:
                    manifest = get_skill(tool_name_to_uid(name))
                display = manifest.name if manifest else name
                args_brief = json.dumps(args, ensure_ascii=False)[:300]
                yield StreamOne(
                    content=f"调用工具 {display}: {args_brief}",
                    stream_event_type=StreamEventType.TOOL_CALL,
                    data={
                        "tool_name": name,
                        "display_name": display,
                        "arguments": args,
                        "nature": manifest.nature if manifest else "static",
                    },
                )
                try:
                    if tool_obj is None:
                        raise ValueError(f"未注册的技能: {name}")
                    # StructuredTool 闭包内已完成参数校验/调用/失败文案(W-10)
                    result = str(await tool_obj.ainvoke(dict(args)))
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
        # 轮数耗尽仍未产出正文(每轮都在调工具): 显式兜底而非静默结束
        if not answer_emitted:
            yield StreamOne(
                content="已达工具调用轮数上限且未生成最终回答, 请精简问题或重试",
                stream_event_type=StreamEventType.ERROR,
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
