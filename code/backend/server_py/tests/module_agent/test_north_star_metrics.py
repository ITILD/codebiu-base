"""北极星指标口径单测(REQ-002 §7.1)

纯函数测试: 不依赖 DB/框架, 固化口径(假完成率是不变量监控, 正常恒为 0)。
"""

from types import SimpleNamespace

from module_agent.service.metrics import build_north_star


def _run(stop_reason: str, usage: dict | None = None, agent_key: str = "research_agent"):
    return SimpleNamespace(
        run_id="r1",
        payload={"stop_reason": stop_reason, "usage": usage or {}, "agent_key": agent_key},
    )


def _item(status: str, passed: bool | None, attempts: int = 1):
    return SimpleNamespace(status=status, verdict_passed=passed, attempts=attempts)


def test_empty_input_returns_zeroed_metrics():
    data = build_north_star([], [])
    assert data["runs"] == 0
    assert data["items"] == 0
    assert data["fake_done_rate"] == 0.0
    assert data["success_rate"] == 0.0
    assert data["cost_per_success"] == {"tokens": 0.0, "tool_calls": 0.0, "elapsed_ms": 0.0}


def test_rates_and_cost_follow_contract():
    events = [
        _run("completed", {"input_tokens": 1000, "output_tokens": 500, "tool_calls": 4, "elapsed_ms": 60000}),
        _run("completed", {"input_tokens": 2000, "output_tokens": 500, "tool_calls": 6, "elapsed_ms": 120000}),
        _run("budget"),
        _run("repeat_action"),
    ]
    items = [
        _item("done", True, attempts=1),
        _item("done", True, attempts=2),
        _item("pending", False, attempts=2),
        _item("pending", None, attempts=0),
    ]
    data = build_north_star(events, items)

    assert data["runs"] == 4
    assert data["items"] == 4
    assert data["success_rate"] == 0.5
    # 首次交卷通过率: 仅 attempts<=1 且通过算, 分母为全部项
    assert data["drilldown"]["first_submit_pass_rate"] == 0.25
    assert data["drilldown"]["budget_hit_rate"] == 0.25
    # 每成功任务成本只统计成功 run
    assert data["cost_per_success"]["tokens"] == 2000.0
    assert data["cost_per_success"]["tool_calls"] == 5.0
    assert data["cost_per_success"]["elapsed_ms"] == 90000.0


def test_fake_done_rate_is_invariant_monitor():
    # 正常: done 一定来自验收通过 → 假完成率恒为 0
    assert build_north_star([], [_item("done", True), _item("pending", False)])[
        "fake_done_rate"
    ] == 0.0
    # 异常: done 但验收未通过 → 必须暴露出来(不变量被破坏)
    assert build_north_star([], [_item("done", False), _item("done", True)])[
        "fake_done_rate"
    ] == 0.5
