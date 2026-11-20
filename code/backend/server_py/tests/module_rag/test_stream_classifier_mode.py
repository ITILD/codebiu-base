"""stream_classifier 模式决策/深度取证事件单测(REQ-019 批次 4-e)

验证 RESOLVE_MODE → MODE_DECISION 与 DEEP → TOOL_CALL 的事件分类与结构化载荷,
不依赖 DB(直接构造 LangGraph StreamEvent)。
"""

from module_rag.do.rag_chat import StreamEventType
from module_rag.utils.llm.stream_classifier import StreamEventClassifier


def _node_end(node: str, output: dict) -> dict:
    """构造 LangGraph on_chain_end 节点事件(与图内 astream 事件同构)"""
    return {
        "event": "on_chain_end",
        "name": node,
        "data": {"output": output},
        "metadata": {"langgraph_node": node},
    }


def _node_start(node: str) -> dict:
    return {
        "event": "on_chain_start",
        "name": node,
        "data": {},
        "metadata": {"langgraph_node": node},
    }


def _classify_one(event: dict):
    return list(StreamEventClassifier().classify(event))


# ── RESOLVE_MODE → MODE_DECISION ─────────────────────────────────


def test_resolve_mode_node_yields_mode_decision():
    events = _classify_one(
        _node_end(
            "resolve_mode",
            {
                "requested_mode": "auto",
                "exec_mode": "deep",
                "mode_reason": "复合问题且工具齐备, 自动升级为深度执行",
            },
        )
    )
    assert len(events) == 1
    one = events[0]
    assert one.stream_event_type is StreamEventType.MODE_DECISION
    assert one.node_name == "resolve_mode"
    assert one.data == {
        "requested_mode": "auto",
        "exec_mode": "deep",
        "reason": "复合问题且工具齐备, 自动升级为深度执行",
    }
    assert one.content == one.data["reason"]


def test_resolve_mode_empty_reason_still_emits():
    """mode_reason 缺失时不崩, 载荷 reason 为空串"""
    events = _classify_one(_node_end("resolve_mode", {}))
    assert len(events) == 1
    assert events[0].data["reason"] == ""


def test_non_node_event_not_misclassified():
    """节点内部子 Runnable 事件(name != 节点名)不产出 MODE_DECISION"""
    event = _node_end("resolve_mode", {"mode_reason": "x"})
    event["name"] = "RunnableSequence"
    assert _classify_one(event) == []


# ── DEEP(deep_agent 节点) → TOOL_CALL(深度取证摘要) ──────────────


def test_deep_node_yields_tool_call_summary():
    output = {
        "deep_evidence": [{"id": "e1"}, {"id": "e2"}],
        "deep_events": [
            {
                "type": "tool_call",
                "tool_name": "kb_search",
                "status": "success",
                "elapsed_ms": 120,
            },
            {
                "type": "skill_masked",
                "tool_name": "kb_search",
                "content": "技能 kb_search 连续失败, 已在本次执行中摘除",
                "data": {"skill_key": "kb_search", "reason": "连续失败"},
            },
        ],
        "deep_stop_reason": "loop_budget",
    }
    events = _classify_one(_node_end("deep_agent", output))
    assert len(events) == 2
    one = events[0]
    assert one.stream_event_type is StreamEventType.TOOL_CALL
    assert one.node_name == "deep_agent"
    data = one.data
    assert data["tool_name"] == "deep_agent"
    assert data["stop_reason"] == "loop_budget"
    assert data["evidence_count"] == 2
    assert len(data["events"]) == 2
    # 文本摘要包含工具名与证据统计
    assert "kb_search" in one.content
    assert "2 条证据" in one.content
    # 技能熔断结构化下发(REQ-002 §6.1: agent.skill_masked)
    masked = events[1]
    assert masked.stream_event_type is StreamEventType.TOOL_CALL
    assert masked.data == {
        "event_type": "agent.skill_masked",
        "skill_key": "kb_search",
        "reason": "连续失败",
    }


def test_deep_node_empty_output_fallback_text():
    events = _classify_one(_node_end("deep_agent", {}))
    assert events[0].content == "深度取证无额外证据"
    assert events[0].data["evidence_count"] == 0


# ── 节点开始状态 ─────────────────────────────────────────────────


def test_node_start_status():
    events = _classify_one(_node_start("search"))
    assert all(e.stream_event_type is StreamEventType.STATUS for e in events)
