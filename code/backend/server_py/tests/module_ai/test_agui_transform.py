"""AG-UI 转换器单测: StreamOne → 官方事件(含 agent.* 协议自定义事件, REQ-019 §8)

纯单元测试(不触 DB): agent.plan_update / agent.verdict 等五拍协议事件必须走
CUSTOM 透传, 不得伪造工具调用组; 普通工具调用仍走 TOOL_CALL_* 事件组。
"""

import json

import pytest
from ag_ui.core import EventType

from module_ai.utils.llm.stream.agui import AguiStreamTransformer
from module_rag.do.rag_chat import StreamEventType, StreamOne


async def _transform(items) -> list[dict]:
    async def source():
        for it in items:
            yield it

    return [
        json.loads(payload)
        async for payload in AguiStreamTransformer().transform(source())
    ]


@pytest.mark.asyncio
async def test_agent_custom_events_passthrough():
    """agent.plan_update / agent.verdict 走 CUSTOM, 不伪造工具调用组"""
    events = await _transform([
        StreamOne(content="任务清单已更新(2 项)", stream_event_type=StreamEventType.TOOL_CALL,
                  data={"event_type": "agent.plan_update", "plan_count": 2}),
        StreamOne(content="t1 验收通过", stream_event_type=StreamEventType.TOOL_CALL,
                  data={"event_type": "agent.verdict", "passed": True, "item_id": "t1"}),
    ])
    names = [e.get("type") for e in events]
    custom = [e for e in events if e.get("type") == EventType.CUSTOM.value]
    assert [c["name"] for c in custom] == ["agent.plan_update", "agent.verdict"]
    assert custom[0]["value"]["plan_count"] == 2
    assert custom[1]["value"]["passed"] is True
    assert EventType.TOOL_CALL_START.value not in names


@pytest.mark.asyncio
async def test_real_tool_call_still_uses_tool_group():
    """普通 TOOL_CALL(data 带 tool_name)仍走 TOOL_CALL_* 事件组"""
    events = await _transform([
        StreamOne(content="调用工具", stream_event_type=StreamEventType.TOOL_CALL,
                  data={"tool_name": "write_file", "arguments": {"path": "a.md"}}),
    ])
    names = [e.get("type") for e in events]
    assert EventType.TOOL_CALL_START.value in names
    assert EventType.TOOL_CALL_RESULT.value in names
    assert EventType.CUSTOM.value not in names
