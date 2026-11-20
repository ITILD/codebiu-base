"""通用有界 ReAct 执行器单测(REQ-019 设计 §3.2)

用假模型 + 假工具验证四重预算、无工具降级、事件产出与结果回填, 不依赖 DB。
"""

import asyncio

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from module_agent.service.agent_runner import (
    AgentRunner,
    ModeConfig,
    RunStatus,
    StopReason,
)


class ScriptedChatModel(BaseChatModel):
    """按脚本依次返回 AIMessage 的假模型(bind_tools 原样返回自身)"""

    script: list[AIMessage] = []
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        self.calls += 1
        idx = min(self.calls - 1, len(self.script) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.script[idx])])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


@tool
def echo(query: str) -> str:
    """回显输入(测试用假工具)"""
    return f"echo:{query}"


def _plan_msg(tool_name: str = "echo") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": {"query": "q"}, "id": f"c-{tool_name}"}],
    )


# ── 预算与降级 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_tools_degrades_to_single_shot():
    """规则 6: 未注册工具时退化为单轮问答, 不进循环"""
    llm = ScriptedChatModel(script=[AIMessage(content="直接回答")])
    result = await AgentRunner().run(
        llm, [HumanMessage(content="hi")], [], ModeConfig(max_loops=3)
    )
    # 降级事件先入列(NO_TOOLS), 单轮问答收尾后终态为 completed
    assert result.events[0]["type"] == "status"
    assert "无可用工具" in result.events[0]["content"]
    assert result.status is RunStatus.SUCCEEDED
    assert result.stop_reason is StopReason.COMPLETED
    assert result.messages[-1].content == "直接回答"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_loop_budget_exhausted():
    """规则 1: 模型持续要求调工具时, 轮次预算触顶优雅收尾"""
    llm = ScriptedChatModel(script=[_plan_msg()])
    result = await AgentRunner().run(
        llm, [HumanMessage(content="hi")], [echo], ModeConfig(max_loops=2, max_model_calls=10)
    )
    assert result.stop_reason is StopReason.LOOP_BUDGET
    assert result.status is RunStatus.EXHAUSTED
    assert result.usage["loops"] == 2


@pytest.mark.asyncio
async def test_tool_budget_exhausted():
    """规则 1: 工具调用预算触顶即停(保留已得证据)"""
    llm = ScriptedChatModel(script=[_plan_msg()])
    # 一次返回多个工具调用, max_tool_calls=1 只允许执行一个
    msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "echo", "args": {"query": "a"}, "id": "c1"},
            {"name": "echo", "args": {"query": "b"}, "id": "c2"},
        ],
    )
    result = await AgentRunner().run(
        llm,
        [HumanMessage(content="hi")],
        [echo],
        ModeConfig(max_loops=2, max_model_calls=10, max_tool_calls=1),
    )
    assert result.stop_reason is StopReason.TOOL_BUDGET
    assert result.usage["tool_calls"] == 1
    assert len(result.tool_calls) == 1


@pytest.mark.asyncio
async def test_model_budget_exhausted():
    llm = ScriptedChatModel(script=[_plan_msg()])
    result = await AgentRunner().run(
        llm, [HumanMessage(content="hi")], [echo], ModeConfig(max_loops=10, max_model_calls=1)
    )
    assert result.stop_reason is StopReason.LOOP_BUDGET or result.stop_reason is StopReason.MODEL_BUDGET


@pytest.mark.asyncio
async def test_completes_when_model_stops_calling_tools():
    """模型不再要求调工具 → completed, ToolMessage 已回填"""
    llm = ScriptedChatModel(script=[_plan_msg(), AIMessage(content="根据证据的回答")])
    result = await AgentRunner().run(
        llm, [HumanMessage(content="hi")], [echo], ModeConfig(max_loops=4)
    )
    assert result.stop_reason is StopReason.COMPLETED
    assert result.messages[-1].content == "根据证据的回答"
    # ToolMessage 已回填(规则 5)
    from langchain_core.messages import ToolMessage

    assert any(isinstance(m, ToolMessage) for m in result.messages)


@pytest.mark.asyncio
async def test_missing_tool_reported_failed():
    """模型点了未注册的工具 → 回填失败 ToolMessage, 不抛异常"""
    llm = ScriptedChatModel(script=[_plan_msg("nope"), AIMessage(content="done")])
    result = await AgentRunner().run(
        llm, [HumanMessage(content="hi")], [echo], ModeConfig(max_loops=4)
    )
    failed = [c for c in result.tool_calls if c["status"] == "failed"]
    assert failed and failed[0]["name"] == "nope"
    assert result.stop_reason is StopReason.COMPLETED


@pytest.mark.asyncio
async def test_tool_timeout_treated_transient():
    """规则 3: 单工具独立硬超时, 超时按 transient 处理"""

    @tool
    async def slow(query: str) -> str:
        """慢工具"""
        await asyncio.sleep(0.3)
        return "ok"

    llm = ScriptedChatModel(script=[_plan_msg("slow"), AIMessage(content="done")])
    result = await AgentRunner().run(
        llm,
        [HumanMessage(content="hi")],
        [slow],
        ModeConfig(max_loops=4, tool_timeout_s=0),  # 0 秒 → 立即超时
    )
    assert result.tool_calls[0]["status"] == "timeout"
    assert "transient" in result.messages[2].content


@pytest.mark.asyncio
async def test_events_emitted():
    """规则 7: 每步产出事件(status/tool_call), 事件列表与 sink 同步"""
    seen: list[dict] = []

    async def sink(event: dict) -> None:
        seen.append(event)

    llm = ScriptedChatModel(script=[_plan_msg(), AIMessage(content="done")])
    result = await AgentRunner().run(
        llm, [HumanMessage(content="hi")], [echo], ModeConfig(max_loops=4), event_sink=sink
    )
    assert result.events
    assert seen == result.events
    assert any(e["type"] == "tool_call" for e in result.events)
