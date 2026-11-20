"""验收闸门(REQ-019 设计 §4.2/§4.4, FEAT-AICAP-016)

五拍协议的**唯一闸门**: 只看产物、证据与验收标准, 不采信执行者自述。
完成由验收判定, 模型没有「完成」按钮。

清单唯一数据对象(Todo/TaskPlan/Contract 三合一, 设计 §4.2):
- Item / Acceptance / Submission / Verdict 是五拍协议的唯一数据模型;
- `write_plan` / `submit` 是运行时控制动词(不是 Skill, 不进 skill_invocation), 见 agent_planner.py。

验收器与 Skill 的关系(设计 §4.4): 验收不经过 SkillRuntime(它不是业务能力, 是事实判定);
但验收执行若调用了业务能力(如生成产物), 该调用仍走 SkillRuntime 以留痕。

四条硬规则(设计 §4.4):
1. 验收优先级: cmd > artifact > judge > 主观描述; 纯主观描述不允许创建;
2. 验收所有权: 验收标准归用户或策略层, acceptance_hash 在失败后不变, verifier 拒绝「改验收过闸」;
3. 判官隔离: judge 只见 goal / 验收 / 产物 / 必要 evidence, 不见执行者思维链与自述;
4. 交卷负载: submit 必须携带 artifacts 与 evidence, 否则验收无物可验。
"""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Awaitable, Callable, Literal

#: cmd 验收的独立硬超时(秒)
CMD_TIMEOUT_S = 120
#: Verdict 原因文本上限
REASON_MAX_CHARS = 500

#: judge 判定回调: 干净上下文 + 只读 goal / 验收 / 产物 / evidence(§4.4 规则 3)
JudgeFn = Callable[["Item", "Submission", str], Awaitable["Verdict"]]
#: human 审批回调(审批拒绝视为未通过, 属外部取消类守卫)
HumanFn = Callable[["Item", "Submission", str], Awaitable["Verdict"]]


class PlanItemStatus(StrEnum):
    """清单项状态: in_progress 由「第一项未完成」隐式表达, 少一个状态少一类 bug"""

    PENDING = "pending"
    DONE = "done"


@dataclass
class Acceptance:
    """验收标准(模型只看到 render() 这一行)"""

    kind: Literal["cmd", "artifact", "judge", "human"]
    spec: str

    def render(self) -> str:
        return f"{self.kind}: {self.spec}"

    def validate(self) -> str | None:
        """创建期校验(§4.4 规则 1): 非法返回原因, 合法返回 None"""
        if self.kind not in ("cmd", "artifact", "judge", "human"):
            return f"验收类型非法: {self.kind}"
        if not self.spec or not self.spec.strip():
            return "验收标准不能为空"
        if self.kind == "cmd" and "\n" in self.spec:
            return "cmd 验收只允许单条命令"
        return None


@dataclass
class Item:
    """清单项(唯一任务对象)"""

    id: str
    goal: str
    acceptance: Acceptance
    status: PlanItemStatus = PlanItemStatus.PENDING
    attempts: int = 0
    last_reason: str = ""       # 上次失败原因, 重试时随任务回灌
    acceptance_hash: str = ""   # 首次交卷时固化, 防止执行者偷偷削弱验收
    verdict_passed: bool | None = None   # 验收事实(北极星: 假完成率统计)
    verdict_reason: str = ""

    @property
    def locked(self) -> bool:
        """已有交卷/验收历史 → 验收标准锁定(只能整体重开, 不能削弱)"""
        return self.attempts > 0 or self.acceptance_hash != ""


@dataclass
class Submission:
    """交卷负载(§4.4 规则 4): artifacts 与 evidence 必填"""

    artifacts: list[str] = field(default_factory=list)  # 产物路径(验收第一取证对象)
    evidence: list[str] = field(default_factory=list)   # 执行过的命令 / 关键输出
    lesson: str = ""                                    # 一行经验(verdict.passed 后才生效)


@dataclass
class Verdict:
    """验收裁决(事实, 不是模型自述)"""

    passed: bool
    reason: str = ""
    evidence: list[str] = field(default_factory=list)


def acceptance_hash(item: Item) -> str:
    """验收标准指纹(削弱检测): kind+spec 的 sha256 前 16 位"""
    payload = json.dumps(
        {"kind": item.acceptance.kind, "spec": item.acceptance.spec.strip()},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


async def verify(
    item: Item,
    submission: Submission,
    workspace: str,
    *,
    judge_fn: JudgeFn | None = None,
    human_fn: HumanFn | None = None,
) -> Verdict:
    """唯一闸门: 按验收类型执行事实判定(§4.4)"""
    if not submission.artifacts and not submission.evidence:
        return Verdict(False, "[approach] 交卷缺少 artifacts 与 evidence, 验收无物可验")

    a = item.acceptance
    if a.kind == "cmd":
        return await _verify_cmd(a.spec, workspace)
    if a.kind == "artifact":
        return await _verify_artifact(a.spec, submission.artifacts, workspace)
    if a.kind == "judge":
        if judge_fn is None:
            return Verdict(False, "[env] judge 判官不可用, 无法验收")
        return await judge_fn(item, submission, workspace)
    if human_fn is None:
        # human 类型默认挂起等待人工: 在无人值守运行时视为未通过, 由运行时发 interrupt
        return Verdict(False, "[env] 等待人工审批(未配置审批回调)")
    return await human_fn(item, submission, workspace)


# ── cmd 验收 ──

async def _verify_cmd(spec: str, workspace: str) -> Verdict:
    """在工作区执行命令, exit code 即裁决"""
    try:
        proc = await asyncio.create_subprocess_shell(
            spec,
            cwd=workspace or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=CMD_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            return Verdict(False, f"[env] 命令执行超时(>{CMD_TIMEOUT_S}s): {spec}")
    except OSError as e:
        return Verdict(False, f"[env] 命令无法启动: {e}")
    text = (out or b"").decode(errors="replace")
    if proc.returncode == 0:
        return Verdict(True, "", [f"cmd:{spec}"])
    if proc.returncode == 127:
        # 依赖缺失/命令不存在 → 环境类(§4.6 前缀约定)
        return Verdict(False, f"[env] 命令不存在(exit=127): {text[-REASON_MAX_CHARS:]}")
    return Verdict(False, f"[approach] cmd 未通过(exit={proc.returncode}): {text[-REASON_MAX_CHARS:]}")


# ── artifact 验收 ──

#: artifact spec 约束语法: "文件路径: 约束, 约束" / 无路径则检查全部交卷产物
#: 约束 = "关键词>=N"(出现次数) / "关键词==N"(精确次数)
_ARTIFACT_RULE = re.compile(r"^\s*([^\s:><=]+)\s*(>=|==)\s*(\d+)\s*$")


def _parse_artifact_spec(spec: str) -> tuple[str | None, list[tuple[str, str, int]]]:
    """解析 'report.md: sections>=3, citations>=5' → (路径|None, [(关键词, op, N)])"""
    target: str | None = None
    body = spec.strip()
    if ":" in body:
        head, body = body.split(":", 1)
        head = head.strip()
        if head and not any(ch in head for ch in "><="):
            target = head
    rules: list[tuple[str, str, int]] = []
    for part in body.split(","):
        if not part.strip():
            continue
        m = _ARTIFACT_RULE.match(part)
        if m is None:
            continue
        rules.append((m.group(1), m.group(2), int(m.group(3))))
    return target, rules


def _resolve_artifact(name: str, submission: Submission, workspace: str) -> Path | None:
    """把交卷产物名解析为工作区内的实际文件(只允许工作区相对路径, 防越界)"""
    for art in submission.artifacts:
        p = Path(art)
        if not p.is_absolute():
            p = Path(workspace) / p
        try:
            p = p.resolve()
            inside = p.is_relative_to(Path(workspace).resolve())
        except (OSError, ValueError):
            continue
        if not inside:
            continue  # 越界产物不取证
        if p.name == Path(name).name or str(p.relative_to(Path(workspace).resolve())) == name:
            if p.is_file():
                return p
    return None


async def _verify_artifact(
    spec: str, artifacts: list[str], workspace: str
) -> Verdict:
    """产物检查: 文件存在 + 关键词计数约束(确定性检查, 不花 token)"""
    target, rules = _parse_artifact_spec(spec)
    if not rules and target is None:
        # 无可解析约束: 只要求列出的产物至少存在一个
        for art in artifacts:
            p = Path(workspace) / art
            if p.is_file():
                return Verdict(True, "", [art])
        return Verdict(False, f"[approach] 产物不存在: {artifacts}")

    if target is not None:
        p = _resolve_artifact(target, Submission(artifacts=artifacts), workspace)
        if p is None:
            return Verdict(False, f"[approach] 产物 {target} 不存在或不在工作区内")
        files = [p]
    else:
        files = [f for f in Path(workspace).rglob("*") if f.is_file()]

    contents = []
    for f in files:
        try:
            contents.append(f.read_text(errors="replace"))
        except OSError:
            contents.append("")

    for keyword, op, expected in rules:
        total = sum(c.count(keyword) for c in contents)
        ok = total >= expected if op == ">=" else total == expected
        if not ok:
            return Verdict(
                False,
                f"[approach] 产物检查未通过: {keyword}{op}{expected} 实际 {total}",
                [f"artifact:{spec}"],
            )
    return Verdict(True, "", [f"artifact:{spec}"])


__all__ = [
    "PlanItemStatus", "Acceptance", "Item", "Submission", "Verdict",
    "acceptance_hash", "verify", "JudgeFn", "HumanFn", "CMD_TIMEOUT_S",
]
