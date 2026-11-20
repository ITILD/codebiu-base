"""五拍协议执行器单测(REQ-019 设计 §4, FEAT-AICAP-015)

用假模型验证: write_plan/submit 控制动词校验、唯一循环、验收闸门驱动完成、
两败改单、验收标准锁定(防削弱)、一屏上下文裁剪、守卫。
不依赖 DB(事件只入内存)。
"""

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from module_agent.service.agent_planner import (
    ONE_SCREEN_BUDGET_CHARS,
    Acceptance,
    Item,
    PlanBudget,
    PlanExecutor,
    _extract_json,
)
from module_agent.service.acceptance import PlanItemStatus, Submission, Verdict, acceptance_hash


class ScriptedChatModel(BaseChatModel):
    """按脚本依次返回 AIMessage 的假模型(bind_tools 原样返回自身)"""

    script: list[AIMessage] = []
    calls: int = 0
    stop_after: int = 10**9

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
        if self.calls > self.stop_after:
            raise RuntimeError("预算耗尽(测试)")
        idx = min(self.calls - 1, len(self.script) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.script[idx])])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


def _write_plan_msg(items: list[dict], reason: str = "initial") -> AIMessage:
    return AIMessage(content="", tool_calls=[{
        "name": "write_plan", "args": {"items": items, "reason": reason}, "id": "c-plan",
    }])


def _submit_msg(item_id: str = "t1", artifacts: list[str] | None = None) -> AIMessage:
    return AIMessage(content="", tool_calls=[{
        "name": "submit",
        "args": {"item_id": item_id, "artifacts": artifacts or [], "evidence": ["did it"]},
        "id": "c-submit",
    }])


def _plain_msg(text: str = "") -> AIMessage:
    return AIMessage(content=text)


def _report_item(workspace_ready: bool = True) -> dict:
    return {
        "id": "t1", "goal": "产出 report.md",
        "acceptance_kind": "artifact", "acceptance_spec": "report.md: DONE>=1",
    }


def _make_write_file_tool(tmp_path):
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field as F

    class Args(BaseModel):
        path: str = F(description="path")
        content: str = F(description="content")

    def _impl(path: str, content: str) -> str:
        (tmp_path / path).write_text(content, encoding="utf-8")
        return f"written {path}"

    return StructuredTool.from_function(
        coroutine=None, func=_impl, name="write_file", args_schema=Args,
        description="写文件到工作区",
    )


async def _append(events, et, iid, payload):
    events.append((et, iid))


# ── write_plan / submit 校验(§4.3) ──────────────────────────────


@pytest.mark.asyncio
async def test_write_plan_rejects_invalid(tmp_path):
    """非法验收类型 / 空标准 → 清单被拒绝, 不产出清单 → no_plan 终止"""
    bad = [{
        "id": "t1", "goal": "x", "acceptance_kind": "guess", "acceptance_spec": "随便",
    }]
    llm = ScriptedChatModel(script=[_write_plan_msg(bad)])
    executor = PlanExecutor()
    result = await executor.run("目标", llm, [], str(tmp_path))
    assert result.stop_reason == "no_plan"
    assert any(e["event_type"] == "write_plan_rejected" for e in result.events)


@pytest.mark.asyncio
async def test_write_plan_locked_acceptance_cannot_weaken(tmp_path):
    """验收标准已锁定(有交卷历史)→ write_plan 修改被拒(防削弱, §4.4 规则 2)"""
    events = []

    async def on_event(et, iid, payload):
        events.append(et)

    executor = PlanExecutor()
    wp, _sp = executor._control_tools(_state_with_locked_item(), on_event)
    # 修改已锁定项的验收标准
    raw = {"items": [{**_locked_raw(), "acceptance_spec": "更弱的标准"}], "reason": "想省事"}
    text = await wp.ainvoke(raw)
    assert "清单被拒绝" in str(text)
    assert "锁定" in str(text)
    assert "write_plan_rejected" in events


def _state_with_locked_item():
    from module_agent.service.agent_planner import _PlanState

    item = Item(
        id="t1", goal="x", acceptance=Acceptance(kind="artifact", spec="report.md: DONE>=1"),
        attempts=1, acceptance_hash=acceptance_hash(Item(
            id="t1", goal="x", acceptance=Acceptance(kind="artifact", spec="report.md: DONE>=1"),
        )),
    )
    return _PlanState([item])


def _locked_raw():
    return {"id": "t1", "goal": "x", "acceptance_kind": "artifact", "acceptance_spec": "report.md: DONE>=1"}


async def _noop(et, iid, p):
    return None


@pytest.mark.asyncio
async def test_submit_must_target_first_pending(tmp_path):
    """规则 1: submit 必须交卷当前第一项未完成任务"""
    executor = PlanExecutor()
    state = _state_with_two_items()
    _wp, sp = executor._control_tools(state, _noop)
    text = await sp.ainvoke({"item_id": "t2", "artifacts": ["a.md"], "evidence": ["x"]})
    assert "第一项未完成任务" in str(text)
    assert state.submission is None


def _state_with_two_items():
    from module_agent.service.agent_planner import _PlanState

    return _PlanState([
        Item(id="t1", goal="x", acceptance=Acceptance(kind="cmd", spec="true")),
        Item(id="t2", goal="y", acceptance=Acceptance(kind="cmd", spec="true")),
    ])


@pytest.mark.asyncio
async def test_submit_requires_payload(tmp_path):
    """规则 4: submit 必须携带 artifacts 与 evidence"""
    executor = PlanExecutor()
    state = _state_with_two_items()
    _wp, sp = executor._control_tools(state, _noop)
    text = await sp.ainvoke({"item_id": "t1", "artifacts": [], "evidence": []})
    assert "无物可验" in str(text)


# ── 唯一循环: 完成由验收判定 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pass_flow(tmp_path):
    """分解 → 执行(写产物) → 交卷 → 验收通过 → done; 模型没有「完成」按钮"""
    tool = _make_write_file_tool(tmp_path)
    llm = ScriptedChatModel(script=[
        _write_plan_msg([_report_item()]),
        _plain_msg(),                                    # 执行轮: 模型先空转一轮被提醒
        AIMessage(content="", tool_calls=[{
            "name": "write_file",
            "args": {"path": "report.md", "content": "DONE here"}, "id": "c-w",
        }]),
        _submit_msg("t1", artifacts=["report.md"], ),
    ])
    events = []
    result = await PlanExecutor(
        on_event=lambda et, iid, p: _append(events, et, iid, p)
    ).run("写报告", llm, [tool], str(tmp_path))
    assert result.ok, result.summary
    assert result.items[0].status is PlanItemStatus.DONE
    assert result.items[0].verdict_passed is True
    assert result.items[0].acceptance_hash != ""
    types = [e["event_type"] for e in result.events]
    assert "write_plan" in types and "submit" in types and "verdict" in types


@pytest.mark.asyncio
async def test_verdict_fail_then_pass(tmp_path):
    """失败回灌 last_reason, 第二次交卷通过; attempts 正确累加"""
    tool = _make_write_file_tool(tmp_path)
    llm = ScriptedChatModel(script=[
        _write_plan_msg([_report_item()]),
        _submit_msg("t1", artifacts=[]),                 # 第一次交卷无产物 → artifact 失败
        _submit_msg("t1", artifacts=[]),                 # 第二次仍失败
        _write_plan_msg([_report_item()], reason="换路径重写产物"),  # 两败改单
        AIMessage(content="", tool_calls=[{
            "name": "write_file", "args": {"path": "report.md", "content": "DONE"}, "id": "c-w",
        }]),
        _submit_msg("t1", artifacts=["report.md"]),
    ])
    result = await PlanExecutor().run("写报告", llm, [tool], str(tmp_path))
    assert result.ok, result.summary
    # 两败后改单发生过(事件里有 revise), item attempts>=2
    assert any(e["event_type"] == "revise" for e in result.events)
    assert result.usage["revisions"] >= 1


@pytest.mark.asyncio
async def test_replan_budget_exhausted(tmp_path):
    """改单上限 3 次, 超限即 replan_budget 终止"""
    tool = _make_write_file_tool(tmp_path)
    plan = [_report_item()]
    script: list[AIMessage] = [_write_plan_msg(plan)]
    # 循环: 交卷失败 → 改单 → 交卷失败 → ... 共 4 次改单(1 次初始 + 3 次 + 第 4 次触发上限)
    for i in range(5):
        script.append(_submit_msg("t1", artifacts=[]))
        script.append(_write_plan_msg([_report_item()], reason=f"revise-{i}"))
    llm = ScriptedChatModel(script=script)
    result = await PlanExecutor().run("写报告", llm, [tool], str(tmp_path))
    assert result.stop_reason == "replan_budget"
    assert result.usage["revisions"] == 3


@pytest.mark.asyncio
async def test_budget_guard_stops(tmp_path):
    """模型持续空转不交卷 → 两败改单失败 → replan_budget 终止(不会无限空转)"""
    tool = _make_write_file_tool(tmp_path)
    llm = ScriptedChatModel(
        script=[_write_plan_msg([_report_item()])] + [_plain_msg("我在想")] * 100
    )
    result = await PlanExecutor().run(
        "写报告", llm, [tool], str(tmp_path),
        budget=PlanBudget(max_model_calls=8),
    )
    assert result.stop_reason == "replan_budget"
    assert result.items[0].status is PlanItemStatus.PENDING
    assert result.items[0].attempts >= 1


def test_budget_guard_unit():
    """守卫三条(确定性代码): 模型/工具预算与重复动作"""
    executor = PlanExecutor()
    import time as _t

    used = {"model_calls": 99, "tool_calls": 0, "loops": 0}
    assert executor._guards(used, PlanBudget(), _t.monotonic(), [], 0) == "budget"
    used = {"model_calls": 0, "tool_calls": 99, "loops": 0}
    assert executor._guards(used, PlanBudget(), _t.monotonic(), [], 0) == "budget"
    used = {"model_calls": 0, "tool_calls": 0, "loops": 0}
    sig = "echo:" + "x" * 10
    assert executor._guards(used, PlanBudget(), _t.monotonic(), [sig] * 4, 0) == "repeat_action"
    assert executor._guards(used, PlanBudget(), _t.monotonic(), [sig] * 4, 9) == "replan_budget"


# ── 一屏上下文(§4.5) ─────────────────────────────────────────────


def test_one_screen_never_truncates_acceptance():
    """验收标准永不截断; 剩余标题先被裁掉"""
    item = Item(id="t1", goal="x" * 3000,
                acceptance=Acceptance(kind="cmd", spec="pytest -q " + "v" * 1500))
    others = [Item(id=f"t{i}", goal=f"任务{i}", acceptance=Acceptance(kind="cmd", spec="true"))
              for i in range(2, 20)]
    text = PlanExecutor._one_screen(item, others, [], "")
    assert "pytest -q" in text and "vvvv" in text  # 验收标准完整
    assert len(text) <= ONE_SCREEN_BUDGET_CHARS + len("pytest -q " + "v" * 1500) + 2000
    assert "剩余任务" not in text  # 放不下先删剩余标题


def test_one_screen_experience_limit():
    """经验最多 3 行"""
    item = Item(id="t1", goal="x", acceptance=Acceptance(kind="cmd", spec="true"))
    exps = [f"经验{i}" for i in range(10)]
    text = PlanExecutor._one_screen(item, [], exps, "")
    assert text.count("经验") >= 1
    assert "经验3" not in text


# ── 一行经验(§4.7) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_experience_recorded_only_on_pass(tmp_path):
    """只在 verdict.passed 后写经验, 且引用来源任务 id"""
    tool = _make_write_file_tool(tmp_path)
    submit_with_lesson = AIMessage(content="", tool_calls=[{
        "name": "submit",
        "args": {"item_id": "t1", "artifacts": ["report.md"], "evidence": ["did"],
                 "lesson": "写报告→先落盘再交卷"},
        "id": "c-s",
    }])
    llm = ScriptedChatModel(script=[
        _write_plan_msg([_report_item()]),
        AIMessage(content="", tool_calls=[{
            "name": "write_file", "args": {"path": "report.md", "content": "DONE"}, "id": "c-w",
        }]),
        submit_with_lesson,
    ])
    events = []
    result = await PlanExecutor(
        on_event=lambda et, iid, p: _append(events, et, iid, p)
    ).run("写报告", llm, [tool], str(tmp_path))
    assert result.ok
    exp_events = [e for e in result.events if e["event_type"] == "experience"]
    assert len(exp_events) == 1
    assert "[source:t1]" in exp_events[0]["lesson"]


# ── 北极星口径 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verdict_facts_recorded(tmp_path):
    """验收事实落 verdict_passed/verdict_reason(假完成率统计口径)"""
    tool = _make_write_file_tool(tmp_path)
    llm = ScriptedChatModel(script=[
        _write_plan_msg([_report_item(), {
            "id": "t2", "goal": "第二步", "acceptance_kind": "cmd", "acceptance_spec": "true",
        }]),
        _submit_msg("t1", artifacts=["report.md"]),   # t1 无产物失败? write_file 未调用
        _submit_msg("t1", artifacts=[]),              # 两败
        _write_plan_msg([_report_item(), {
            "id": "t2", "goal": "第二步", "acceptance_kind": "cmd", "acceptance_spec": "true",
        }], reason="拆分重试"),
        AIMessage(content="", tool_calls=[{
            "name": "write_file", "args": {"path": "report.md", "content": "DONE"}, "id": "c-w",
        }]),
        _submit_msg("t1", artifacts=["report.md"]),   # t1 通过
        _submit_msg("t2"),                            # t2 cmd 验收 true → 通过
    ])
    result = await PlanExecutor().run("两步任务", llm, [tool], str(tmp_path))
    assert result.ok, result.summary
    verdicts = {i.id: i.verdict_passed for i in result.items}
    assert verdicts == {"t1": True, "t2": True}


def test_extract_json():
    """judge 兜底输出解析: 容忍代码围栏"""
    assert _extract_json('```json\n{"passed": true, "reason": "ok"}\n```')["passed"] is True
    assert _extract_json("garbage") == {}


# ── 实时投影与北极星埋点(§4.8/§4.9) ──────────────────────────────


@pytest.mark.asyncio
async def test_state_change_events_carry_items_snapshot(tmp_path):
    """状态变化事件(write_plan/verdict)附清单快照: 运行时据此实时投影(§4.8)"""
    tool = _make_write_file_tool(tmp_path)
    llm = ScriptedChatModel(script=[
        _write_plan_msg([_report_item()]),
        AIMessage(content="", tool_calls=[{
            "name": "write_file", "args": {"path": "report.md", "content": "DONE"}, "id": "c-w",
        }]),
        _submit_msg("t1", artifacts=["report.md"]),
    ])
    payloads: list[tuple[str, dict]] = []
    from module_agent.service.runner import AgentRunnerService

    async def on_event(et, iid, p):
        payloads.append((et, p))
        return None

    result = await PlanExecutor(on_event=on_event).run("写报告", llm, [tool], str(tmp_path))
    assert result.ok
    wp_payload = next(p for et, p in payloads if et == "write_plan")
    vd_payload = next(p for et, p in payloads if et == "verdict")
    assert wp_payload["items"][0]["id"] == "t1"
    assert wp_payload["items"][0]["status"] == "pending"
    assert wp_payload["items"][0]["acceptance_spec"] == "report.md: DONE>=1"
    assert vd_payload["items"][0]["status"] == "done"
    assert vd_payload["items"][0]["verdict_passed"] is True
    # 快照可被 runner 的投影直接消费(字段齐备)
    assert AgentRunnerService._plan_event_stream("verdict", "t1", vd_payload) is not None


@pytest.mark.asyncio
async def test_usage_tokens_accounted(tmp_path):
    """模型 token 用量计入 usage(北极星②: 每成功任务成本, §4.9)"""
    tool = _make_write_file_tool(tmp_path)
    llm = ScriptedChatModel(script=[
        _write_plan_msg([_report_item()]),
        AIMessage(
            content="", tool_calls=[{
                "name": "write_file",
                "args": {"path": "report.md", "content": "DONE"}, "id": "c-w",
            }],
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        ),
        AIMessage(
            content="", tool_calls=[{
                "name": "submit", "args": {"item_id": "t1", "artifacts": ["report.md"],
                                           "evidence": ["did"]}, "id": "c-s",
            }],
            usage_metadata={"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
        ),
    ])
    result = await PlanExecutor().run("写报告", llm, [tool], str(tmp_path))
    assert result.ok
    assert result.usage["input_tokens"] == 150
    assert result.usage["output_tokens"] == 30
    assert result.usage["model_calls"] >= 2
