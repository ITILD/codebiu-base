"""通用有界 ReAct 执行器(REQ-019 设计 §3.2, 业务无关)

分层边界(设计 §3.1):
- 本文件**不感知任何具体业务**: 只负责有界循环、预算计数、墙钟截止、分步思考档位切换、
  工具结果回填与事件产出。
- 业务侧(`module_rag/service/deep_agent.py` 等)负责: 注册哪些工具、工具结果如何转成证据、
  如何排序、如何注入回答上下文。

硬规则(设计 §3.2 表):
1. 四重预算(轮次/模型调用/工具调用/墙钟)任一触顶即优雅收尾, 返回 `stop_reason`, 不无限重试(CA-12);
2. 循环内每轮开头比对墙钟截止, 超时即停并输出已得证据;
3. 单次工具调用独立硬超时(默认 30s), 超时按 `transient` 处理;
4. 分步思考档位: 规划/选工具步骤用 `think_level_plan`, 理解工具结果/填参步骤用 `think_level_answer`,
   判定依据 = 最近一条消息是否为 `ToolMessage`;
5. 工具结果以 `ToolMessage` 回填, **不进用户可见对话流**; 超长结果先截断预览;
6. 未注册任何工具时退化为单轮问答, 不空转预算;
7. 每步产出事件(工具名/参数摘要/结果摘要/档位/耗时), 供前端「思考过程」折叠展示。
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, ToolMessage
from langchain_core.tools import BaseTool

from module_ai.utils.llm.chat.think import with_think_mode

logger = logging.getLogger(__name__)

#: 工具结果回填给模型时的字符上限(超出截断, 防上下文膨胀)
TOOL_RESULT_MAX_CHARS = 6000
#: 事件里携带的结果预览长度
TOOL_EVENT_PREVIEW_CHARS = 400
#: 单次工具调用独立硬超时(秒)
DEFAULT_TOOL_TIMEOUT_S = 30


class RunStatus(StrEnum):
    """执行状态"""

    SUCCEEDED = "succeeded"   # 正常收尾(无工具调用/模型给出终答)
    DEGRADED = "degraded"     # 降级收尾(工具绑定失败/模型调用失败, 已有部分结果)
    EXHAUSTED = "exhausted"   # 预算触顶优雅收尾
    TIMEOUT = "timeout"       # 墙钟超时


class StopReason(StrEnum):
    """收尾原因(可观测, 前端展示"为什么停了")"""

    COMPLETED = "completed"        # 模型给出终答
    NO_TOOLS = "no_tools"          # 未注册工具, 退化为单轮问答
    LOOP_BUDGET = "loop_budget"    # 轮次预算触顶
    MODEL_BUDGET = "model_budget"  # 模型调用预算触顶
    TOOL_BUDGET = "tool_budget"    # 工具调用预算触顶
    TIMEOUT = "timeout"            # 墙钟超时
    MODEL_ERROR = "model_error"    # 模型调用异常
    BIND_ERROR = "bind_error"      # 工具绑定异常


@dataclass
class ModeConfig:
    """执行预算与思考档位配置(来自内置 Agent 的 `chat_modes`)"""

    max_loops: int = 6
    max_model_calls: int = 8
    max_tool_calls: int = 12
    wall_clock_s: int = 90
    think_level_plan: str = "high"    # 规划/选工具步骤的思考档位
    think_level_answer: str = "off"   # 理解工具结果/填参步骤的思考档位
    tool_timeout_s: int = DEFAULT_TOOL_TIMEOUT_S
    max_tokens: int | None = None      # 历史裁剪上限(None=用工具默认)


@dataclass
class AgentRunResult:
    """执行结果"""

    status: RunStatus = RunStatus.SUCCEEDED
    stop_reason: StopReason = StopReason.COMPLETED
    messages: list[AnyMessage] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        """是否正常收尾(非降级/非超时)"""
        return self.status in (RunStatus.SUCCEEDED, RunStatus.EXHAUSTED)


#: 事件下发回调(异步)
EventSink = Callable[[dict], Awaitable[None]]


class AgentRunner:
    """通用有界 ReAct 执行器(业务无关)"""

    async def run(
        self,
        llm: BaseChatModel,
        messages: list[AnyMessage],
        tools: list[BaseTool],
        cfg: ModeConfig,
        *,
        event_sink: EventSink | None = None,
    ) -> AgentRunResult:
        """执行有界 ReAct 循环

        :param llm: 对话模型
        :param messages: 消息列表(含系统提示词)
        :param tools: 业务侧已注册的工具
        :param cfg: 预算与思考档位
        :param event_sink: 过程事件回调(可选)
        :return: AgentRunResult
        """
        result = AgentRunResult(messages=list(messages))
        if not tools:
            # 规则 6: 无工具退化为单轮问答, 不空转预算
            result.stop_reason = StopReason.NO_TOOLS
            await self._emit(
                event_sink,
                {
                    "type": "status",
                    "status": "degraded",
                    "content": "无可用工具, 退化为单轮问答",
                },
                result.events,
            )
            await self._single_shot(llm, messages, cfg, result)
            return result

        try:
            plan_llm = with_think_mode(llm, cfg.think_level_plan).bind_tools(tools)
            answer_llm = with_think_mode(llm, cfg.think_level_answer).bind_tools(tools)
        except Exception as e:  # 绑定失败: 降级为单轮问答
            logger.warning("智能体绑定工具失败: %s", e)
            result.status = RunStatus.DEGRADED
            result.stop_reason = StopReason.BIND_ERROR
            result.error = f"工具绑定失败: {e}"
            await self._single_shot(llm, messages, cfg, result)
            return result

        started = time.monotonic()
        loops = 0
        model_calls = 0
        tool_calls = 0

        while True:
            # 规则 1/2: 轮次与模型调用预算 + 每轮开头墙钟检查
            if loops >= cfg.max_loops:
                result.status = RunStatus.EXHAUSTED
                result.stop_reason = StopReason.LOOP_BUDGET
                await self._emit(
                    event_sink,
                    {
                        "type": "status",
                        "status": "exhausted",
                        "content": f"已达执行轮次上限 {cfg.max_loops}, 停止继续取证",
                    },
                    result.events,
                )
                break
            if model_calls >= cfg.max_model_calls:
                result.status = RunStatus.EXHAUSTED
                result.stop_reason = StopReason.MODEL_BUDGET
                await self._emit(
                    event_sink,
                    {
                        "type": "status",
                        "status": "exhausted",
                        "content": f"已达模型调用上限 {cfg.max_model_calls}, 停止继续取证",
                    },
                    result.events,
                )
                break
            elapsed = time.monotonic() - started
            if elapsed > cfg.wall_clock_s:
                result.status = RunStatus.TIMEOUT
                result.stop_reason = StopReason.TIMEOUT
                await self._emit(
                    event_sink,
                    {
                        "type": "status",
                        "status": "timeout",
                        "content": f"执行超过 {cfg.wall_clock_s}s, 已停止并输出已得证据",
                    },
                    result.events,
                )
                break

            loops += 1
            model_calls += 1
            # 规则 4: 最近一条是 ToolMessage → 只需理解结果, 关思考; 否则规划, 开思考
            is_result_step = isinstance(result.messages[-1], ToolMessage) if result.messages else False
            think_level = cfg.think_level_answer if is_result_step else cfg.think_level_plan
            current_llm = answer_llm if is_result_step else plan_llm

            step_started = time.monotonic()
            try:
                ai_message = await current_llm.ainvoke(result.messages)
            except Exception as e:
                logger.warning("智能体规划调用失败: %s", e)
                result.status = RunStatus.DEGRADED
                result.stop_reason = StopReason.MODEL_ERROR
                result.error = f"规划调用失败: {e}"
                await self._emit(
                    event_sink,
                    {
                        "type": "status",
                        "status": "failed",
                        "content": f"规划调用失败: {e}",
                        "elapsed_ms": int((time.monotonic() - step_started) * 1000),
                    },
                    result.events,
                )
                break

            result.messages.append(ai_message)
            calls = list(getattr(ai_message, "tool_calls", None) or [])
            if not calls:
                result.stop_reason = StopReason.COMPLETED
                break

            for call in calls:
                # 规则 1: 工具调用预算触顶即停(优雅收尾, 保留已得证据)
                if tool_calls >= cfg.max_tool_calls:
                    result.status = RunStatus.EXHAUSTED
                    result.stop_reason = StopReason.TOOL_BUDGET
                    await self._emit(
                        event_sink,
                        {
                            "type": "status",
                            "status": "exhausted",
                            "content": f"工具调用达到上限 {cfg.max_tool_calls}, 停止调用",
                        },
                        result.events,
                    )
                    break

                name = str(call.get("name") or "")
                args = call.get("args") or {}
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                call_id = str(call.get("id") or f"{name}-{tool_calls}")
                tool = next((t for t in tools if t.name == name), None)

                if tool is None:
                    result_text = f"工具不存在: {name}"
                    status = "failed"
                else:
                    tool_calls += 1
                    result_text, status = await self._call_tool(tool, args, cfg)

                # 规则 5: 结果以 ToolMessage 回填, 不进用户可见对话流
                result.messages.append(
                    ToolMessage(content=self._truncate(result_text), tool_call_id=call_id)
                )
                result.tool_calls.append(
                    {
                        "name": name,
                        "args": args,
                        "status": status,
                        "result_preview": result_text[:TOOL_EVENT_PREVIEW_CHARS],
                    }
                )
                await self._emit(
                    event_sink,
                    {
                        "type": "tool_call",
                        "tool_name": name,
                        "arguments": args,
                        "status": status,
                        "content": self._tool_event_text(name, args, result_text),
                        "result_preview": result_text[:TOOL_EVENT_PREVIEW_CHARS],
                        "think_level": think_level,
                        "elapsed_ms": int((time.monotonic() - step_started) * 1000),
                    },
                    result.events,
                )
            else:
                # 本轮工具全部执行完, 继续下一轮规划
                continue
            # 工具预算触顶时跳出外层循环
            break

        result.usage = {
            "loops": loops,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "wall_clock_s": cfg.wall_clock_s,
        }
        return result

    # ── 内部 ──

    async def _call_tool(
        self, tool: BaseTool, args: dict, cfg: ModeConfig
    ) -> tuple[str, str]:
        """调用单个工具(独立硬超时, 超时按 transient 处理)"""
        try:
            raw = await asyncio.wait_for(
                tool.ainvoke(args), timeout=cfg.tool_timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning("智能体工具 %s 超时(>%ss)", tool.name, cfg.tool_timeout_s)
            return f"[调用失败:transient] 工具执行超时(>{cfg.tool_timeout_s}s), 请重试或换一种方式。", "timeout"
        except Exception as e:
            logger.warning("智能体工具 %s 执行失败: %s", tool.name, e)
            return f"[调用失败:permanent] 工具执行失败: {e}", "failed"
        return str(raw if raw is not None else ""), "success"

    async def _single_shot(
        self,
        llm: BaseChatModel,
        messages: list[AnyMessage],
        cfg: ModeConfig,
        result: AgentRunResult,
    ) -> None:
        """无工具/绑定失败时的单轮问答降级"""
        try:
            ai_message = await with_think_mode(llm, cfg.think_level_answer).ainvoke(messages)
        except Exception as e:
            logger.warning("单轮问答失败: %s", e)
            result.status = RunStatus.DEGRADED
            result.stop_reason = StopReason.MODEL_ERROR
            result.error = f"模型调用失败: {e}"
            return
        result.messages.append(ai_message)
        result.stop_reason = StopReason.COMPLETED

    @staticmethod
    def _truncate(text: str) -> str:
        """工具结果截断(防上下文膨胀)"""
        if len(text) <= TOOL_RESULT_MAX_CHARS:
            return text
        return (
            text[:TOOL_RESULT_MAX_CHARS]
            + f"\n...[结果已截断, 原始长度 {len(text)} 字符]"
        )

    @staticmethod
    def _tool_event_text(name: str, args: dict, result: str) -> str:
        """工具事件文案(参数摘要 + 结果摘要)"""
        query = str(args.get("query") or args.get("code") or args.get("keyword") or "")[:120]
        head = f"{name}({query})" if query else name
        return f"{head}\n{result[:TOOL_EVENT_PREVIEW_CHARS]}"

    @staticmethod
    async def _emit(
        sink: EventSink | None, event: dict, events: list[dict]
    ) -> None:
        """产出事件(先入结果再下发, 下发失败不影响主流程)"""
        events.append(event)
        if sink is None:
            return
        try:
            await sink(event)
        except Exception as e:  # pragma: no cover - 事件下发不应影响执行
            logger.warning("事件下发失败(忽略): %s", e)
