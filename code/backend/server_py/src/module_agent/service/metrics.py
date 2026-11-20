"""北极星指标聚合(REQ-002 §7.1)

纯函数: 输入 `run_finished` 事件(run 粒度) + `agent_plan_item`(项粒度), 输出指标口径。
抽出的目的: 口径只有一处、可单测, 不依赖 DB 与 FastAPI。

口径:
- 假完成率 = done 且 verdict_passed≠true / done —— **不变量监控**, 正常恒为 0;
- 任务成功率 = stop_reason=completed 的 run / 总 run;
- 每成功任务成本 = 成功 run 的平均 tokens / 工具调用 / 耗时;
- 下钻: 首次交卷通过率 = attempts<=1 且验收通过 / 总项; 预算触顶率 = stop_reason=budget / 总 run。
"""

from typing import Any, Iterable


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def build_north_star(events: Iterable[Any], items: Iterable[Any]) -> dict[str, Any]:
    """聚合北极星三项 + 两项下钻

    :param events: AgentPlanEvent(run_finished) 对象/桩, 需 payload
    :param items:  AgentPlanItem 对象/桩, 需 status/attempts/verdict_passed
    """
    events = list(events)
    items = list(items)

    runs = len(events)
    success = [e for e in events if (e.payload or {}).get("stop_reason") == "completed"]
    budget_hit = [e for e in events if (e.payload or {}).get("stop_reason") == "budget"]

    done = [i for i in items if i.status == "done"]
    fake_done = [i for i in done if i.verdict_passed is not True]
    first_pass = [i for i in items if i.verdict_passed is True and (i.attempts or 0) <= 1]

    usages = [(e.payload or {}).get("usage") or {} for e in success]
    return {
        "fake_done_rate": _rate(len(fake_done), len(done)),
        "success_rate": _rate(len(success), runs),
        "cost_per_success": {
            "tokens": _avg([
                int(u.get("input_tokens", 0) or 0) + int(u.get("output_tokens", 0) or 0)
                for u in usages
            ]),
            "tool_calls": _avg([int(u.get("tool_calls", 0) or 0) for u in usages]),
            "elapsed_ms": _avg([int(u.get("elapsed_ms", 0) or 0) for u in usages]),
        },
        "drilldown": {
            "first_submit_pass_rate": _rate(len(first_pass), len(items)),
            "budget_hit_rate": _rate(len(budget_hit), runs),
        },
        "runs": runs,
        "items": len(items),
    }
