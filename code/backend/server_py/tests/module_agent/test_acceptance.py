"""验收闸门单测(REQ-019 设计 §4.4, FEAT-AICAP-016)

验证四类验收(cmd/artifact/judge/human)、acceptance_hash 防削弱、交卷负载校验。
"""

import pytest

from module_agent.service.acceptance import (
    Acceptance,
    Item,
    PlanItemStatus,
    Submission,
    Verdict,
    acceptance_hash,
    verify,
)


def _item(kind: str = "cmd", spec: str = "true", locked: bool = False) -> Item:
    item = Item(id="t1", goal="完成任务", acceptance=Acceptance(kind=kind, spec=spec))
    if locked:
        item.attempts = 1
        item.acceptance_hash = acceptance_hash(item)
    return item


# ── 数据对象 ─────────────────────────────────────────────────────


def test_acceptance_render_and_validate():
    """模型只看到 render() 这一行; 纯主观/非法类型不允许创建(规则 1)"""
    a = Acceptance(kind="cmd", spec="pytest -q")
    assert a.render() == "cmd: pytest -q"
    assert Acceptance(kind="cmd", spec="").validate() is not None
    assert Acceptance(kind="multi", spec="x").validate() is not None
    assert Acceptance(kind="judge", spec="按 rubric 评审").validate() is None


def test_acceptance_hash_stable():
    """同标准同指纹, 微改 spec 指纹变化(削弱检测基础)"""
    a = _item("cmd", "pytest -q")
    b = _item("cmd", "pytest -q")
    c = _item("cmd", "pytest -q tests/")
    assert acceptance_hash(a) == acceptance_hash(b)
    assert acceptance_hash(a) != acceptance_hash(c)


def test_locked_item_rejects_change():
    """已有交卷历史 → 验收标准锁定(write_plan 校验依据)"""
    assert _item(locked=True).locked is True
    assert _item(locked=False).locked is False


# ── 交卷负载(规则 4) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_submission_rejected():
    """无 artifacts 且无 evidence → 验收无物可验"""
    verdict = await verify(_item(), Submission(), "/tmp")
    assert verdict.passed is False
    assert "无物可验" in verdict.reason


# ── cmd 验收 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_pass_and_fail(tmp_path):
    ok = await verify(_item("cmd", "true"), Submission(evidence=["ran"]), str(tmp_path))
    assert ok.passed is True
    fail = await verify(_item("cmd", "false"), Submission(evidence=["ran"]), str(tmp_path))
    assert fail.passed is False
    assert "cmd 未通过" in fail.reason


@pytest.mark.asyncio
async def test_cmd_env_error_prefix(tmp_path):
    """环境类失败用 [env] 前缀(§4.6 失败原因前缀约定)"""
    verdict = await verify(_item("cmd", "nonexistent_cmd_xyz"), Submission(evidence=["x"]), str(tmp_path))
    assert verdict.passed is False
    assert verdict.reason.startswith("[env]") or "无法启动" in verdict.reason


# ── artifact 验收 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_artifact_constraints(tmp_path):
    (tmp_path / "report.md").write_text("# A\n# A\n# A\ncite cite cite\ncite\n", encoding="utf-8")
    item = _item("artifact", "report.md: A>=3, cite>=4")
    sub = Submission(artifacts=["report.md"], evidence=["wrote"])
    verdict = await verify(item, sub, str(tmp_path))
    assert verdict.passed is True

    item2 = _item("artifact", "report.md: A>=10")
    verdict2 = await verify(item2, sub, str(tmp_path))
    assert verdict2.passed is False
    assert "产物检查未通过" in verdict2.reason


@pytest.mark.asyncio
async def test_artifact_missing_file(tmp_path):
    verdict = await verify(
        _item("artifact", "missing.md: A>=1"),
        Submission(artifacts=["missing.md"], evidence=["x"]), str(tmp_path),
    )
    assert verdict.passed is False
    assert "不存在" in verdict.reason


@pytest.mark.asyncio
async def test_artifact_out_of_workspace(tmp_path, tmp_path_factory):
    """越界产物不取证(安全: 只允许工作区相对路径)"""
    outside = tmp_path_factory.mktemp("outside") / "leak.md"
    outside.write_text("A", encoding="utf-8")
    verdict = await verify(
        _item("artifact", "leak.md: A>=1"),
        Submission(artifacts=[str(outside)], evidence=["x"]), str(tmp_path),
    )
    assert verdict.passed is False


# ── judge 验收(判官隔离) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_isolated_callback():
    """judge 只走回调(干净上下文), 不采信执行者自述"""
    seen = {}

    async def judge_fn(item, submission, workspace):
        seen["goal"] = item.goal
        return Verdict(True, "rubric 达标")

    verdict = await verify(
        _item("judge", "按 rubric 评审"),
        Submission(artifacts=["a.md"], evidence=["自述完成"]), "/tmp",
        judge_fn=judge_fn,
    )
    assert verdict.passed is True
    assert seen["goal"] == "完成任务"


@pytest.mark.asyncio
async def test_judge_unavailable():
    """judge 判官不可用 → 未通过(不降级为主观采信)"""
    verdict = await verify(_item("judge", "rubric"), Submission(evidence=["x"]), "/tmp")
    assert verdict.passed is False
    assert "judge 判官不可用" in verdict.reason


# ── human 验收 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_human_approval_callback():
    async def human_fn(item, submission, workspace):
        return Verdict(False, "审批拒绝")

    verdict = await verify(_item("human", "需人工确认"), Submission(evidence=["x"]), "/tmp",
                           human_fn=human_fn)
    assert verdict.passed is False


@pytest.mark.asyncio
async def test_human_no_callback_holds():
    """未配置审批回调 → 挂起视为未通过, 交由运行时发 interrupt"""
    verdict = await verify(_item("human", "需人工确认"), Submission(evidence=["x"]), "/tmp")
    assert verdict.passed is False
    assert "人工" in verdict.reason


# ── 状态 ─────────────────────────────────────────────────────────


def test_status_only_pending_done():
    """§4.2: in_progress 由「第一项未完成」隐式表达, 只有两个状态"""
    assert {s.value for s in PlanItemStatus} == {"pending", "done"}
