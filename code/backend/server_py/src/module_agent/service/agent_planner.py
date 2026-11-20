"""五拍协议执行器(REQ-019 设计 §4, FEAT-AICAP-015)

任务型 ai_agent(`execution_strategy=plan_execute`)按「一条清单、一个循环、一道闸门」执行:
模型只做分解、执行、交卷、按失败原因改单; **完成由验收判定, 模型没有「完成」按钮**。

分层边界(设计 §4.1「模型侧做减法, 运行时侧做加法」):
- 模型侧: 分解 / 执行 / 交卷 / 按失败原因改单 —— 自主权: 分解自由、改单自由、执行自由;
  唯一被收回的权利是「宣布完成」;
- 运行时侧(本文件): 记录事件、执行工具、验收、压缩上下文、预算、门控 —— 不替模型思考。

三个不可妥协项: 完成必须是验收事实; 计划必须驱动取任务; 上下文必须一屏。

控制动词(§4.3): `write_plan` / `submit` 是运行时控制工具, **不是 Skill**:
不注册进业务 Skill 表, 不进 skill_invocation, 由本执行器直接处理。
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from module_agent.service.acceptance import (
    CMD_TIMEOUT_S,
    Acceptance,
    Item,
    JudgeFn,
    PlanItemStatus,
    Submission,
    Verdict,
    acceptance_hash,
    verify,
)

logger = logging.getLogger(__name__)

#: 一屏上下文硬预算(字符, 约 1.5k token)
ONE_SCREEN_BUDGET_CHARS = 4000
#: 同一(工具+参数)哈希连续重复超阈值即停(重复动作守卫)
REPEAT_ACTION_LIMIT = 4
#: 改单上限(两败改单也有上限)
REPLAN_BUDGET = 3
#: 交卷原因/裁决原因截断
REASON_MAX = 300

#: 写入 system prompt 的全部行为规则(§4.3 五行, 不再多说教)
PLAN_RULES = """\
1. 只做清单第一项未完成任务；动手前先确认它的验收标准。
2. 怎么做完全由你决定：步骤、工具、技能不限；用技能先看目录、再加载全文。
3. 做完调用 submit 交卷。完成与否由验收判定，你没有"完成"按钮。
4. 验收失败：按原因修复后重新交卷；同一项失败两次，必须先修改清单。
5. 清单可增删改，但验收标准只能加强、不能削弱；每次改动附一句原因。"""

#: 事件回调: (event_type, item_id, payload) —— 供 agent_plan_event 落库与 AG-UI 下发
PlanEventCb = Callable[[str, str, dict], Awaitable[None]]


# ── 控制动词入参 schema ──

class _PlanItemIn(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="清单项ID")
    goal: str = Field(min_length=1, description="任务目标(一句话)")
    acceptance_kind: str = Field(description="验收类型: cmd/artifact/judge/human")
    acceptance_spec: str = Field(min_length=1, description='验收标准, 如 "pytest -q" 或 "report.md: sections>=3"')


class WritePlanArgs(BaseModel):
    items: list[_PlanItemIn] = Field(min_length=1, description="清单项列表(全量替换)")
    reason: str = Field(min_length=1, description="本次清单改动的一句话原因")


class SubmitArgs(BaseModel):
    item_id: str = Field(min_length=1, description="交卷的清单项ID(必须是当前第一项未完成任务)")
    artifacts: list[str] = Field(default_factory=list, description="产物路径(相对工作区)")
    evidence: list[str] = Field(default_factory=list, description="执行过的命令/关键输出")
    lesson: str = Field(default="", description="一行经验(情形→做法), 验收通过后才生效")


@dataclass
class PlanBudget:
    """全局预算(守卫一: 预算, 全部确定性代码, 不花 token、不进 prompt)"""

    max_model_calls: int = 40
    max_tool_calls: int = 60
    wall_clock_s: int = 600
    tool_timeout_s: int = CMD_TIMEOUT_S


@dataclass
class PlanRunResult:
    """运行结果(北极星埋点口径: 假完成率=标记done但验收失败比例, 直接由 items.verdict_* 统计)"""

    run_id: str = ""
    status: str = "succeeded"          # succeeded/stopped/failed
    stop_reason: str = "completed"     # completed/budget/cancelled/repeat_action/replan_budget/no_plan
    items: list[Item] = field(default_factory=list)
    summary: str = ""
    events: list[dict] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.stop_reason == "completed"


class _PlanState:
    """运行期共享状态(submit 闭包与主循环共用)"""

    def __init__(self, items: list[Item]):
        self.items = items
        self.submission: Submission | None = None


class PlanExecutor:
    """五拍协议执行器(分解 → 执行 → 交卷 → 验收 → 改单)"""

    def __init__(
        self,
        *,
        judge_fn: JudgeFn | None = None,
        human_fn: Callable[[Item, Submission, str], Awaitable[Verdict]] | None = None,
        on_event: PlanEventCb | None = None,
    ):
        """
        :param judge_fn: judge 型验收回调(判官隔离: 只见 goal/验收/产物/evidence;
                         未提供时用传入 llm 的干净上下文兜底)
        :param human_fn: human 型验收回调(审批拒绝/超时视为未通过)
        :param on_event: 事件回调(agent_plan_event 落库 + AG-UI 下发)
        """
        self.judge_fn = judge_fn
        self.human_fn = human_fn
        self.on_event = on_event

    # ── 主循环(§4.6 唯一循环) ──

    async def run(
        self,
        goal: str,
        llm: BaseChatModel,
        tools: list[BaseTool],
        workspace: str,
        budget: PlanBudget | None = None,
        *,
        run_id: str = "",
        conversation_id: str = "",
    ) -> PlanRunResult:
        """执行五拍协议主循环

        :param goal: 总任务目标(用户请求)
        :param tools: 业务侧工具(已按条件注册; write_plan/submit 由执行器自带, 不传)
        :param workspace: 工作区(cmd/artifact 验收的取证目录)
        """
        budget = budget or PlanBudget()
        result = PlanRunResult(run_id=run_id or f"plan-{int(time.time() * 1000)}")
        state = _PlanState([])
        experiences: list[str] = []
        revisions = 0
        started = time.monotonic()
        used = {"model_calls": 0, "tool_calls": 0, "loops": 0, "input_tokens": 0, "output_tokens": 0}
        repeat_hist: list[str] = []

        async def record(event_type: str, item_id: str, payload: dict) -> None:
            # 状态变化事件附清单快照: 供运行时实时投影(§4.8 单向投影)与前端 agent.plan_update
            extra: dict = {}
            if event_type in ("write_plan", "verdict", "revise", "guard_stop"):
                extra["items"] = [self._item_snapshot(i) for i in state.items]
            event = {"event_type": event_type, "item_id": item_id, **payload, **extra}
            result.events.append(event)
            if self.on_event is not None:
                try:
                    await self.on_event(event_type, item_id, {
                        **payload, **extra,
                        "run_id": result.run_id, "conversation_id": conversation_id,
                    })
                except Exception as e:  # 事件落库失败不影响执行
                    logger.warning("五拍协议事件落库失败(忽略): %s", e)

        write_plan_tool, submit_tool = self._control_tools(state, record)

        # 第一拍: 分解 —— 直到产出合法清单(计划必须驱动取任务)
        ok = await self._plan_call(
            f"总任务目标：{goal}\n\n请用 write_plan 把任务分解为带验收标准的清单。"
            f"验收类型优先级：cmd > artifact > judge > human；纯主观描述不允许创建。",
            llm, [write_plan_tool], used=used,
        )
        if not ok or not state.items:
            result.stop_reason = "no_plan"
            result.status = "failed"
            result.summary = "模型未产出合法清单, 任务终止"
            result.items = list(state.items)
            result.usage = self._usage(started, used, budget, revisions)
            return result
        await record("write_plan", "", {"reason": "initial", "count": len(state.items)})
        result.items = list(state.items)

        # 唯一循环: 只做第一项未完成任务(§4.6)
        while True:
            item = next((i for i in state.items if i.status is PlanItemStatus.PENDING), None)
            if item is None:
                result.stop_reason = "completed"
                break
            if guard_reason := self._guards(used, budget, started, repeat_hist, revisions):
                result.stop_reason = guard_reason
                result.status = "stopped"
                await record("guard_stop", item.id, {"reason": guard_reason})
                break

            # 第二拍 执行 + 第三拍 交卷(react 阶段, 一屏上下文)
            screen = self._one_screen(item, state.items, experiences, self._skill_digest(tools))
            state.submission = None
            await self._react_phase(goal, screen, llm, tools, [write_plan_tool, submit_tool],
                                    state, used, budget, repeat_hist)
            submission = state.submission
            if submission is None:
                verdict = Verdict(False, "[approach] 未在阶段预算内交卷")
            else:
                # 第四拍: 验收(唯一闸门; 首次交卷固化 acceptance_hash, 防削弱)
                if not item.acceptance_hash:
                    item.acceptance_hash = acceptance_hash(item)
                verdict = await verify(
                    item, submission, workspace,
                    judge_fn=self.judge_fn or self._default_judge(llm),
                    human_fn=self.human_fn,
                )
                if verdict.passed:
                    used["model_calls"] += 1  # judge 走了模型, 计入预算口径

            # 裁决先落状态再记事件: 快照携带最新验收事实(实时投影依赖, §4.8)
            item.verdict_passed = verdict.passed
            item.verdict_reason = verdict.reason
            if verdict.passed:
                item.status = PlanItemStatus.DONE
            else:
                item.attempts += 1
                item.last_reason = verdict.reason
            result.items = list(state.items)
            await record("verdict", item.id, {
                "passed": verdict.passed, "reason": verdict.reason[:REASON_MAX],
                "attempts": item.attempts,
            })

            if verdict.passed:
                # 一行经验: 只在 verdict.passed 后写(§4.7)
                if submission is not None and submission.lesson.strip():
                    lesson = f"{submission.lesson.strip()} [source:{item.id}]"
                    experiences.append(lesson)
                    await record("experience", item.id, {"lesson": lesson})
                continue

            # 第五拍: 两败必改单(§4.6 静默规则; attempts 已在裁决时累加)
            if item.attempts >= 2:
                if revisions >= REPLAN_BUDGET:
                    result.stop_reason = "replan_budget"
                    result.status = "stopped"
                    await record("guard_stop", item.id, {"reason": "replan_budget"})
                    break
                revised = await self._revise(goal, llm, state, item, verdict,
                                             write_plan_tool, used)
                await record("revise", item.id, {"ok": revised, "attempts": item.attempts})
                if not revised:
                    result.stop_reason = "replan_budget"
                    result.status = "stopped"
                    break
                revisions += 1
                result.items = list(state.items)

        result.items = list(state.items)
        result.summary = self._summary(state.items)
        result.usage = self._usage(started, used, budget, revisions)
        return result

    # ── 控制动词(§4.3: 运行时控制工具, 不是 Skill) ──

    def _control_tools(self, state: _PlanState, record: PlanEventCb) -> tuple[BaseTool, BaseTool]:
        """write_plan / submit: 运行时校验 schema、记录事件; 模型无法自行宣布完成"""

        async def write_plan(
            items: list[_PlanItemIn], reason: str
        ) -> str:
            new_items: list[Item] = []
            errors: list[str] = []
            existing = {i.id: i for i in state.items}
            for raw in items:
                acc = Acceptance(kind=raw.acceptance_kind, spec=raw.acceptance_spec)
                if err := acc.validate():
                    errors.append(f"{raw.id}: {err}")
                    continue
                old = existing.get(raw.id)
                if old is not None and old.locked and (
                    old.acceptance.spec.strip() != acc.spec.strip()
                    or old.acceptance.kind != acc.kind
                ):
                    errors.append(
                        f"{raw.id}: 验收标准已锁定(已有交卷历史), 只能加强不能修改; "
                        f"如需变更请拆分新项或升级人工"
                    )
                    continue
                new_items.append(Item(
                    id=raw.id, goal=raw.goal, acceptance=acc,
                    status=old.status if old else PlanItemStatus.PENDING,
                    attempts=old.attempts if old else 0,
                    last_reason=old.last_reason if old else "",
                    acceptance_hash=old.acceptance_hash if old else "",
                    verdict_passed=old.verdict_passed if old else None,
                    verdict_reason=old.verdict_reason if old else "",
                ))
            if errors:
                await record("write_plan_rejected", "", {"errors": errors})
                return "清单被拒绝:\n" + "\n".join(errors)
            state.items[:] = new_items
            return f"清单已生效(共 {len(new_items)} 项), 原因: {reason}"

        async def submit(
            item_id: str,
            artifacts: list[str] | None = None,
            evidence: list[str] | None = None,
            lesson: str = "",
        ) -> str:
            artifacts = artifacts or []
            evidence = evidence or []
            current = next((i for i in state.items if i.status is PlanItemStatus.PENDING), None)
            if current is None:
                return "无待办清单项, 无需交卷"
            if item_id != current.id:
                return f"交卷对象必须是当前第一项未完成任务 {current.id}(规则 1)"
            if not artifacts and not evidence:
                return "submit 必须携带 artifacts 与 evidence, 否则验收无物可验"
            state.submission = Submission(
                artifacts=artifacts, evidence=evidence, lesson=lesson
            )
            await record("submit", current.id, {
                "artifacts": artifacts, "evidence_count": len(evidence),
            })
            return "交卷已受理, 等待验收裁决。完成与否由验收判定, 你没有「完成」按钮。"

        return (
            StructuredTool.from_function(
                coroutine=write_plan, name="write_plan", args_schema=WritePlanArgs,
                description="创建/替换/修订任务清单(全量替换)。每次改动附一句原因。",
            ),
            StructuredTool.from_function(
                coroutine=submit, name="submit", args_schema=SubmitArgs,
                description="交卷请求验收。必须携带 artifacts 与 evidence。",
            ),
        )

    def _default_judge(self, llm: BaseChatModel) -> JudgeFn:
        """judge 型验收兜底: 干净上下文, 只见 goal/验收/产物/evidence(§4.4 规则 3)"""

        async def _judge(item: Item, submission: Submission, workspace: str) -> Verdict:
            files_text = ""
            for art in submission.artifacts:
                try:
                    files_text += f"\n--- {art} ---\n{_read_artifact(workspace, art)[:2000]}\n"
                except Exception:
                    files_text += f"\n--- {art} --- (无法读取)"
            prompt = (
                "你是独立的验收判官。只依据下列事实判定任务是否达成, 不采信任何自述。\n"
                f"目标：{item.goal}\n验收标准(rubric)：{item.acceptance.spec}\n"
                f"产物：{json.dumps(submission.artifacts, ensure_ascii=False)}\n"
                f"证据：{json.dumps(submission.evidence[:10], ensure_ascii=False)}\n"
                f"产物内容：{files_text}\n"
                '只输出 JSON: {"passed": true, "reason": "一句话原因"}'
            )
            try:
                resp = await llm.ainvoke([HumanMessage(content=prompt)])
                data = _extract_json(str(getattr(resp, "content", "") or ""))
                return Verdict(bool(data.get("passed")), str(data.get("reason", ""))[:REASON_MAX])
            except Exception as e:
                return Verdict(False, f"[env] judge 调用失败: {e}")
        return _judge

    # ── react 阶段(执行+交卷, 有界) ──

    async def _react_phase(
        self, goal: str, screen: str, llm: BaseChatModel,
        tools: list[BaseTool], control_tools: list[BaseTool],
        state: _PlanState, used: dict, budget: PlanBudget, repeat_hist: list[str],
    ) -> None:
        """单任务的执行阶段: 业务工具自由调用, 以 submit 收束; 预算触顶优雅返回"""
        all_tools = list(tools) + list(control_tools)
        try:
            runnable = llm.bind_tools(all_tools)
        except Exception as e:
            logger.warning("五拍协议绑定工具失败: %s", e)
            return
        messages: list[AnyMessage] = [
            SystemMessage(content=PLAN_RULES),
            HumanMessage(content=f"总任务目标：{goal}\n\n{screen}\n\n开始执行当前任务。"),
        ]
        # 无新产物守卫: 连续 N 轮无 submit/无产物即停, 不发进度提醒
        idle_rounds = 0
        while used["model_calls"] < budget.max_model_calls and used["tool_calls"] < budget.max_tool_calls:
            used["model_calls"] += 1
            used["loops"] += 1
            try:
                ai = await runnable.ainvoke(messages)
                self._acc_tokens(ai, used)
            except Exception as e:
                logger.warning("五拍协议模型调用失败: %s", e)
                return
            messages.append(ai)
            calls = list(getattr(ai, "tool_calls", None) or [])
            if not calls:
                idle_rounds += 1
                if idle_rounds >= 2:
                    return  # 两轮无动作即收尾, 由主循环按「未交卷」处理
                messages.append(HumanMessage(
                    content="请调用 submit 交卷(必须携带 artifacts 与 evidence)。"
                ))
                continue
            idle_rounds = 0
            for call in calls:
                name = str(call.get("name") or "")
                args = call.get("args") or {}
                call_id = str(call.get("id") or name)
                tool = next((t for t in all_tools if t.name == name), None)
                if tool is None:
                    text = f"工具不存在: {name}"
                else:
                    used["tool_calls"] += 1
                    text = await self._run_tool(tool, args, budget)
                # 重复动作守卫只统计业务工具(控制动词豁免)
                if name not in ("write_plan", "submit"):
                    repeat_hist.append(
                        name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True)[:200]
                    )
                else:
                    repeat_hist.clear()
                messages.append(ToolMessage(content=text[:6000], tool_call_id=call_id))
            if state.submission is not None:
                return  # 已交卷, 回到主循环验收

    async def _run_tool(self, tool: BaseTool, args: dict, budget: PlanBudget) -> str:
        try:
            raw = await asyncio.wait_for(tool.ainvoke(dict(args)), timeout=budget.tool_timeout_s)
            return str(raw if raw is not None else "")
        except asyncio.TimeoutError:
            return f"[调用失败:transient] 工具执行超时(>{budget.tool_timeout_s}s)"
        except Exception as e:
            return f"[调用失败:permanent] {e}"

    # ── 第一拍分解 / 两败改单(只绑 write_plan 的单次规划调用) ──

    async def _plan_call(
        self, prompt: str, llm: BaseChatModel, tools: list[BaseTool], *, used: dict
    ) -> bool:
        """让模型产出 write_plan 调用并应用校验; 成功返回 True"""
        try:
            runnable = llm.bind_tools(tools)
        except Exception as e:
            logger.warning("五拍协议绑定 write_plan 失败: %s", e)
            return False
        used["model_calls"] += 1
        try:
            ai = await runnable.ainvoke([
                SystemMessage(content=PLAN_RULES), HumanMessage(content=prompt),
            ])
            self._acc_tokens(ai, used)
        except Exception as e:
            logger.warning("五拍协议规划调用失败: %s", e)
            return False
        for call in (getattr(ai, "tool_calls", None) or []):
            if str(call.get("name")) == "write_plan":
                raw = call.get("args") or {}
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        return False
                try:
                    text = await tools[0].ainvoke(raw)
                except Exception as e:
                    logger.warning("write_plan 应用失败: %s", e)
                    return False
                return "清单已生效" in str(text)
        return False

    async def _revise(
        self, goal: str, llm: BaseChatModel, state: _PlanState, item: Item,
        verdict: Verdict, write_plan_tool: BaseTool, used: dict,
    ) -> bool:
        """两败改单: 拆分 / 换路径 / 换验收(只能加强) / 升级人工"""
        listing = "\n".join(
            f"- {i.id} [{i.status.value}](attempts={i.attempts}) {i.goal} 验收: {i.acceptance.render()}"
            for i in state.items
        )
        ok = await self._plan_call(
            f"总任务目标：{goal}\n当前清单：\n{listing}\n\n"
            f"失败项：{item.id}（已失败 {item.attempts} 次）\n失败原因：{verdict.reason}\n\n"
            f"必须先修改清单：拆分、换路径、加强验收(不能削弱)，或引入人工审批(human)。"
            f"用 write_plan 提交修订后的完整清单。",
            llm, [write_plan_tool], used=used,
        )
        return ok and any(i.status is PlanItemStatus.PENDING for i in state.items)

    # ── 守卫三条(§4.6, 全确定性代码, 不花 token、不进 prompt) ──

    def _guards(
        self, used: dict, budget: PlanBudget, started: float,
        repeat_hist: list[str], revisions: int,
    ) -> str:
        """返回守卫停止原因, 未触发返回空串"""
        if used["model_calls"] >= budget.max_model_calls:
            return "budget"
        if used["tool_calls"] >= budget.max_tool_calls:
            return "budget"
        if time.monotonic() - started > budget.wall_clock_s:
            return "budget"
        if revisions > REPLAN_BUDGET:
            return "replan_budget"
        # 重复动作守卫: 连续相同 (tool+args) 哈希超阈值即停(轮询类工具由调用方豁免)
        if len(repeat_hist) >= REPEAT_ACTION_LIMIT:
            tail = repeat_hist[-REPEAT_ACTION_LIMIT:]
            if len(set(tail)) == 1:
                return "repeat_action"
        return ""

    # ── 一屏上下文(§4.5) ──

    @staticmethod
    def _one_screen(
        item: Item | None, items: list[Item], experiences: list[str], skill_digest: str
    ) -> str:
        """模型每轮严格只看到: 当前项全文 / 剩余标题一行 / 经验≤3行 / 技能目录。

        永不注入: 全量历史清单、规则说教、能力图谱、决策快照、完整 ReAct 转录。
        裁剪顺序固定: 当前项 > 验收标准 > 最近失败原因 > 剩余标题 > 经验 > 技能目录。
        验收标准永不截断; 放不下先删剩余标题再删经验 —— 计划拆得太碎的报警器。
        """
        current_block = ""
        if item is not None:
            current_block = (
                f"当前任务：{item.id} {item.goal}\n"
                f"验收标准：{item.acceptance.render()}（验收标准永不截断）\n"
                f"尝试次数：{item.attempts}"
                + (f"\n上次失败原因：{item.last_reason}" if item.last_reason else "")
            )
        remaining = [
            f"- {i.id} {i.goal}"
            for i in items
            if i.status is PlanItemStatus.PENDING and (item is None or i.id != item.id)
        ]
        exp_block = "\n".join(experiences[:3]) if experiences else ""
        # 超预算裁剪: 先删剩余标题(整块), 再删经验, 技能目录最后
        while remaining and len(current_block) + sum(map(len, remaining)) + len(exp_block) + len(skill_digest) > ONE_SCREEN_BUDGET_CHARS:
            remaining = remaining[:-1]
        if len(exp_block) + len(current_block) + len(skill_digest) > ONE_SCREEN_BUDGET_CHARS:
            exp_block = ""
        parts = [b for b in (current_block,
                             "剩余任务：\n" + "\n".join(remaining) if remaining else "",
                             "经验：\n" + exp_block if exp_block else "",
                             "技能目录：\n" + skill_digest if skill_digest else "") if b]
        return "\n\n".join(parts)

    @staticmethod
    def _skill_digest(tools: list[BaseTool]) -> str:
        """技能目录: name + description(digest 变化才更新, 由调用方缓存)"""
        return "\n".join(
            f"- {t.name}: {t.description}"
            for t in tools if t.name not in ("write_plan", "submit")
        )

    @staticmethod
    def _usage(started: float, used: dict, budget: PlanBudget, revisions: int) -> dict:
        return {
            **used,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "wall_clock_s": budget.wall_clock_s,
            "revisions": revisions,
        }

    @staticmethod
    def _item_snapshot(item: Item) -> dict:
        """清单项快照(实时投影/前端 agent.plan_update 载荷, §4.8)"""
        return {
            "id": item.id, "goal": item.goal,
            "acceptance_kind": item.acceptance.kind,
            "acceptance_spec": item.acceptance.spec,
            "acceptance_hash": item.acceptance_hash,
            "status": item.status.value, "attempts": item.attempts,
            "last_reason": item.last_reason,
            "verdict_passed": item.verdict_passed,
            "verdict_reason": item.verdict_reason,
        }

    @staticmethod
    def _acc_tokens(ai: Any, used: dict) -> None:
        """累计模型 token 用量(北极星②: 每成功任务成本, §4.9)"""
        meta = getattr(ai, "usage_metadata", None) or {}
        used["input_tokens"] += int(meta.get("input_tokens", 0) or 0)
        used["output_tokens"] += int(meta.get("output_tokens", 0) or 0)

    @staticmethod
    def _summary(items: list[Item]) -> str:
        done = sum(1 for i in items if i.status is PlanItemStatus.DONE)
        passed = sum(1 for i in items if i.verdict_passed is True)
        return f"清单 {len(items)} 项: 完成 {done}, 验收通过 {passed}"


# ── 辅助 ──

def _read_artifact(workspace: str, art: str) -> str:
    """读取交卷产物(仅工作区内, 越界抛异常)"""
    p = Path(art)
    if not p.is_absolute():
        p = Path(workspace) / p
    p = p.resolve()
    if not p.is_relative_to(Path(workspace).resolve()):
        raise ValueError("产物越界")
    return p.read_text(errors="replace")


def _extract_json(text: str) -> dict:
    """从模型输出提取 JSON(容忍代码围栏)"""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


__all__ = [
    "PlanExecutor", "PlanBudget", "PlanRunResult", "PLAN_RULES",
    "ONE_SCREEN_BUDGET_CHARS", "REPEAT_ACTION_LIMIT", "REPLAN_BUDGET",
]
