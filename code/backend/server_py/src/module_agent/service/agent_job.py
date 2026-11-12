"""AgentJobService: static_agent 批处理 job 运行时(REQ-018, 设计 §3.3/W-3/W-12)

执行模型(W-12: 与 ai_agent 同用 LangGraph StateGraph, static_agent 只是分支
全部显式、无模型节点的图; 断点续跑接 PostgreSQL checkpointer 属批次 2, 本批
以 agent_job_run.steps_state 为状态载体先行内建):
- 每步 = 一批 Skill 调用按 fan_out 并发展开; 步骤间线性推进(depends_on 校验)
- 批内条件在编排层表达(CA-07/W-2): when 步骤级准入 / skip_if 展开项过滤,
  判定表达式与结果随步骤状态落库(可追溯)
- job 整体默认 queued(agent_job_execute 任务, worker 内执行); 步骤以 inline
  长超时直接执行(避免 worker 池嵌套排队死锁)
- 步骤产物(markdown/blocks)按 item_key 在 job 内存传递, 不落观测表(摘要落库)
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from sqlalchemy import update as sa_update

from common.config.db import db_manager
from module_agent.agents import get_agent_job
from module_agent.agents.expr import ExprError, evaluate
from module_agent.agents.manifest import AgentJobManifest, AgentStepDef
from module_agent.do.agent_job_run import AgentJobRun, JobRunStatus
from module_agent.service.skill_runtime import SkillContext, SkillRuntime
from module_agent.skills.registry import get_skill

logger = logging.getLogger(__name__)


def _merge_steps(left: dict, right: dict) -> dict:
    """LangGraph state reducer: 步骤状态字典按 step_id 合并"""
    merged = dict(left)
    merged.update(right)
    return merged


_resolver_cache: dict[str, Any] = {}


def _load_input_resolver(ref: str) -> Any:
    """动态加载展开项输入准备器('模块路径:函数名', 协程函数, 进程内缓存)"""
    cached = _resolver_cache.get(ref)
    if cached is not None:
        return cached
    import importlib

    module_path, _, func_name = ref.partition(":")
    if not module_path or not func_name:
        raise ValueError(f"input_resolver 引用非法: {ref}")
    fn = getattr(importlib.import_module(module_path), func_name)
    if not asyncio.iscoroutinefunction(fn):
        raise ValueError(f"input_resolver 必须是协程函数: {ref}")
    _resolver_cache[ref] = fn
    return fn


async def _cleanup_paths(paths: list[str]) -> None:
    """job 结束清理临时物化文件(失败不抛出)"""
    import shutil

    for path in paths:
        try:
            await asyncio.to_thread(shutil.rmtree, path, True)
        except Exception as e:  # 清理失败不影响 job 终态
            logger.debug("临时文件清理失败(忽略) %s: %s", path, e)


class _JobState(TypedDict):
    """job 图状态(产物不进 state, 经闭包产物区内存传递)"""

    job_run_id: str
    user_id: str
    input: dict
    priority_class: str
    entry: str
    steps: Annotated[dict, _merge_steps]
    aborted: bool
    # 断点续跑(批次 2): 上次运行的步骤状态(item 级已完成判定依据)
    prev_steps: dict


class AgentJobService:
    """job Agent 运行时(submit 投递 / run 执行 / 观测回写)"""

    def __init__(self, runtime: SkillRuntime | None = None):
        self.runtime = runtime or SkillRuntime()

    # ################ 提交 ################

    async def submit(
        self,
        agent_key: str,
        job_input: dict,
        ctx: SkillContext,
        mode: str = "auto",
    ) -> dict:
        """提交 job: 幂等建 run → queued(默认)/inline 执行

        :return: {job_run_id, agent_key, status, task_id}
        """
        manifest = get_agent_job(agent_key)
        if manifest is None:
            raise ValueError(f"未注册的 job Agent: {agent_key}")

        # Agent 级幂等: agent_key + 展开项业务键集合(同集合的活跃 job 复用, W-3)
        item_keys = sorted(
            str(it.get("document_id")) for it in (job_input.get("documents") or [])
        )
        fingerprint = hashlib.sha256(
            json.dumps([agent_key, manifest.version, item_keys], ensure_ascii=False).encode()
        ).hexdigest()
        reused = await self._find_active_run(fingerprint)
        if reused is not None:
            return {
                "job_run_id": reused.job_run_id, "agent_key": agent_key,
                "status": reused.status, "task_id": reused.task_id, "reused": True,
            }

        run = AgentJobRun(
            agent_key=agent_key,
            agent_version=manifest.version,
            status=JobRunStatus.PENDING,
            priority_class=manifest.runtime_policy.get("priority_class", "batch"),
            idempotency_key=fingerprint,
            input_summary={
                # 完整展开项元数据(document_id/file_path/filename/size_hint 等):
                # worker resume 时经 _load_input 还原完整 job 输入(步骤产物不在此)
                "documents": job_input.get("documents") or [],
                "project_ids": job_input.get("project_ids") or [],
            },
            user_id=ctx.user_id,
            entry=ctx.entry,
        )
        async with db_manager.db_rel.session_factory() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)

        if mode == "inline":
            return await self.run(run.job_run_id)

        # 默认 queued: 先落 agent_job_run(pending) 再落 task_queue 投递(CA-10 同构)
        from module_task.dao.task import TaskQueueDao
        from module_task.do.task import TaskQueue, TaskQueueCreate
        from module_task.service.task import TaskQueueService

        priority = {"interactive": 7, "standard": 5, "batch": 2}.get(run.priority_class, 2)
        try:
            task = await TaskQueueService(TaskQueueDao()).create(
                TaskQueueCreate(
                    name=f"Agent job: {manifest.name}",
                    task_type="agent_job_execute",
                    payload={"job_run_id": run.job_run_id},
                    priority=priority,
                ),
                ctx.user_id,
            )
        except Exception as e:
            message = f"job 任务投递失败: {e}"
            await self._mark(run.job_run_id, status=JobRunStatus.FAILED, error=message[:1000])
            return {"job_run_id": run.job_run_id, "agent_key": agent_key, "status": "failed", "task_id": None}

        async with db_manager.db_rel.session_factory() as session:
            task_row = await session.get(TaskQueue, task.id)
            if task_row is not None:
                task_row.invocation_id = run.job_run_id
            run_row = await session.get(AgentJobRun, run.job_run_id)
            if run_row is not None:
                run_row.task_id = task.id
            await session.commit()
        return {
            "job_run_id": run.job_run_id, "agent_key": agent_key,
            "status": "pending", "task_id": task.id,
        }

    # ################ 执行 ################

    async def run(self, job_run_id: str) -> dict:
        """执行 job(inline 直跑与 worker resume 共用): 建图 → ainvoke → 终态回写"""
        from langgraph.graph import END, START, StateGraph

        async with db_manager.db_rel.session_factory() as session:
            run = await session.get(AgentJobRun, job_run_id)
            if run is None:
                raise ValueError(f"agent_job_run 不存在: {job_run_id}")
            if run.status not in (JobRunStatus.PENDING, JobRunStatus.FAILED):
                logger.info("job 已处理(幂等跳过): %s status=%s", job_run_id, run.status)
                return {"job_run_id": job_run_id, "status": run.status}
            agent_key, user_id, priority, entry = (
                run.agent_key, run.user_id, run.priority_class, run.entry or "web"
            )

        manifest = get_agent_job(agent_key)
        if manifest is None:
            await self._finish(job_run_id, JobRunStatus.FAILED, error=f"job Agent 已下线: {agent_key}")
            return {"job_run_id": job_run_id, "status": "failed"}

        await self._mark(job_run_id, status=JobRunStatus.RUNNING, set_started=True)

        # 断点续跑(批次 2): 产物从 checkpoint 恢复(consume 跨进程可续);
        # 已完成项判定依据 steps_state(prev_steps); attempt 递增隔离 checkpointer 线程
        checkpoint_data = dict(run.checkpoint or {}) if (run := await self.get(job_run_id)) else {}
        attempt = int(checkpoint_data.get("attempt") or 0) + 1
        artifacts: dict[str, dict[str, dict]] = {
            sid: dict(per)
            for sid, per in (checkpoint_data.get("artifacts") or {}).items()
        }
        prev_steps = dict(run.steps_state or {})

        ctx = SkillContext(user_id=user_id, priority_class=priority, entry=entry)

        graph = StateGraph(_JobState)
        for step in manifest.steps:
            graph.add_node(step.id, self._make_step_node(manifest, step, artifacts, ctx, prev_steps))
        prev = START
        for step in manifest.steps:
            graph.add_edge(prev, step.id)
            prev = step.id
        graph.add_edge(prev, END)
        # W-12 定案: static_agent 与 ai_agent 同用 LangGraph + PostgreSQL checkpointer;
        # job 断点续跑以 steps_state/checkpoint 为准(图每次执行独立线程, 不重放旧图)
        checkpointer = None
        try:
            from module_rag.config.checkpointer import get_checkpointer

            checkpointer = await get_checkpointer()
        except Exception as e:
            logger.warning("checkpointer 不可用, 本次执行不落图检查点(忽略): %s", e)
        app = graph.compile(checkpointer=checkpointer)

        initial: _JobState = {
            "job_run_id": job_run_id, "user_id": user_id,
            "input": await self._load_input(job_run_id),
            "priority_class": priority, "entry": entry,
            "steps": {}, "aborted": False, "prev_steps": prev_steps,
        }
        # attempt 落库(下次续跑 attempt+1, checkpointer 线程隔离)
        await self._merge_checkpoint(job_run_id, {"attempt": attempt})
        try:
            final_state = await app.ainvoke(
                initial, config={"configurable": {"thread_id": f"{job_run_id}:{attempt}"}}
            )
            steps = final_state.get("steps", {})
            aborted = bool(final_state.get("aborted"))
            any_failed = any(
                s.get("status") == "failed" for s in steps.values()
            )
            status = JobRunStatus.FAILED if (aborted or any_failed) else JobRunStatus.SUCCEEDED
            error = None
            if aborted:
                error = "fail_fast 步骤失败, job 已中止"
            elif any_failed:
                failed_steps = [sid for sid, s in steps.items() if s.get("status") == "failed"]
                error = f"部分步骤失败: {', '.join(failed_steps)}(明细见 steps_state)"
            result = {
                "steps": {
                    sid: s.get("counts", {}) for sid, s in steps.items()
                }
            }
            await self._finish(job_run_id, status, result=result, error=error)
            return {"job_run_id": job_run_id, "status": status.value, "steps": result["steps"]}
        except Exception as e:
            logger.error("job 执行异常 %s: %s", job_run_id, e, exc_info=True)
            await self._finish(
                job_run_id, JobRunStatus.FAILED, error=f"{type(e).__name__}: {e}"[:1000]
            )
            return {"job_run_id": job_run_id, "status": "failed"}
        finally:
            # 清理 input_resolver 物化的临时文件(文档临时目录等)
            await _cleanup_paths(artifacts.pop("__cleanup__", []))

    async def resume(self, job_run_id: str, task_id: str) -> dict:
        """Task Executor 回调入口(worker 领取 agent_job_execute 后)"""
        from module_task.tasks import update_task_fields

        await update_task_fields(
            task_id, status="running", message="Agent job 执行中", set_started=True
        )
        outcome = await self.run(job_run_id)
        status = outcome.get("status")
        if status == "succeeded":
            await update_task_fields(
                task_id, status="success", progress=100, message="job 完成",
                result=outcome, set_finished=True,
            )
        else:
            await update_task_fields(
                task_id, status="failed", error=(outcome.get("error") or "job 失败(见 agent_job_run)"),
                set_finished=True,
            )
        return outcome

    async def resume_run(self, job_run_id: str, user_id: str) -> dict:
        """断点续跑(REQ-018 批次 2): 失败/取消的 job 从已完成项之后继续

        - 已成功项直接复用(steps_state 判定), 产物从 checkpoint 恢复(consume 可续)
        - 图以新 attempt 线程重跑, 不重放旧检查点
        """
        run = await self.get(job_run_id)
        if run is None:
            raise ValueError(f"agent_job_run 不存在: {job_run_id}")
        if run.user_id != user_id:
            from common.utils.fastapi_ex.exceptions import ForbiddenError

            raise ForbiddenError("仅提交者可续跑该 job")
        if run.status not in (JobRunStatus.FAILED, JobRunStatus.CANCELLED):
            raise ValueError(f"仅失败/取消的 job 可续跑(当前: {run.status})")
        await self._mark(job_run_id, status=JobRunStatus.PENDING, error=None)
        # 清终态时间, 重置进度口径
        async with db_manager.db_rel.session_factory() as session:
            row = await session.get(AgentJobRun, job_run_id)
            if row is not None:
                row.finished_at = None
                await session.commit()
        return await self.run(job_run_id)

    # ################ 步骤节点 ################

    def _make_step_node(
        self,
        manifest: AgentJobManifest,
        step: AgentStepDef,
        artifacts: dict[str, dict[str, dict]],
        ctx: SkillContext,
        prev_steps: dict,
    ):
        """构建步骤节点: when 准入 → fan_out 展开 → 逐项(并发) 断点跳过/skip_if/调用"""

        async def node(state: _JobState) -> dict:
            step_state: dict[str, Any] = {"status": "running"}
            try:
                # fail_fast 已中止 → 后续步骤整步跳过
                if state.get("aborted"):
                    step_state.update(status="skipped", reason="aborted_by_fail_fast")
                    await self._persist_step(state["job_run_id"], step.id, step_state)
                    return {"steps": {step.id: step_state}, "aborted": True}

                # 步骤级准入 when(引用前序步骤聚合摘要)
                if step.when is not None:
                    when_ctx = {
                        sid: self._step_summary(s) for sid, s in state.get("steps", {}).items()
                    }
                    try:
                        when_result = bool(evaluate(step.when, when_ctx))
                    except ExprError as e:
                        step_state.update(status="failed", error=f"when 表达式非法: {e}")
                        await self._persist_step(state["job_run_id"], step.id, step_state)
                        return {"steps": {step.id: step_state}, "aborted": step.on_error == "fail_fast"}
                    step_state["when"] = {"expr": step.when, "result": when_result}
                    if not when_result:
                        step_state.update(status="skipped", reason="when=false")
                        await self._persist_step(state["job_run_id"], step.id, step_state)
                        return {"steps": {step.id: step_state}}

                # 展开: fan_out 字段列表逐项; 未声明则单项(整个 input 为一项)
                job_input = state.get("input", {})
                if step.fan_out:
                    items = [dict(it) for it in (job_input.get(step.fan_out) or [])]
                else:
                    items = [dict(job_input)]
                if not items:
                    step_state.update(status="succeeded", counts={"total": 0}, items={})
                    await self._persist_step(state["job_run_id"], step.id, step_state)
                    return {"steps": {step.id: step_state}}

                # 依赖步骤的同键产物摘要(skip_if 求值上下文)
                dep_summaries: dict[str, dict[str, dict]] = {}
                for dep in step.depends_on:
                    dep_summaries[dep] = {
                        key: self._item_summary(env) for key, env in (artifacts.get(dep) or {}).items()
                    }

                max_parallel = int(manifest.runtime_policy.get("max_parallel") or 4)
                semaphore = asyncio.Semaphore(max_parallel)
                item_states: dict[str, dict] = {}
                # 断点续跑(批次 2): 上次运行已成功的项直接复用(不重复执行/不重复计费)
                prev_items = (state.get("prev_steps", {}).get(step.id, {}) or {}).get("items") or {}

                async def _run_item(item: dict) -> None:
                    item_key_value = str(item.get(step.item_key) or "")
                    resumed = prev_items.get(item_key_value)
                    if resumed is not None and resumed.get("status") == "succeeded":
                        item_states[item_key_value] = {**resumed, "resumed": True}
                        return
                    async with semaphore:
                        item_state = await self._run_step_item(
                            step, item, item_key_value, dep_summaries, ctx, artifacts
                        )
                    item_states[item_key_value] = item_state

                await asyncio.gather(*(_run_item(item) for item in items))

                counts = {
                    "total": len(item_states),
                    "succeeded": sum(1 for s in item_states.values() if s["status"] == "succeeded"),
                    "failed": sum(1 for s in item_states.values() if s["status"] == "failed"),
                    "skipped": sum(1 for s in item_states.values() if s["status"] == "skipped"),
                }
                aborted = step.on_error == "fail_fast" and counts["failed"] > 0
                step_state.update(
                    status="failed" if counts["failed"] and step.on_error == "fail_fast" else "succeeded",
                    items=item_states,
                    counts=counts,
                )
                await self._persist_step(
                    state["job_run_id"], step.id, step_state, artifacts.get(step.id)
                )
                return {"steps": {step.id: step_state}, "aborted": aborted}
            except Exception as e:
                logger.error("job 步骤异常 %s/%s: %s", manifest.agent_key, step.id, e, exc_info=True)
                step_state.update(status="failed", error=f"{type(e).__name__}: {e}"[:500])
                await self._persist_step(state["job_run_id"], step.id, step_state)
                return {"steps": {step.id: step_state}, "aborted": True}

        return node

    async def _run_step_item(
        self,
        step: AgentStepDef,
        item: dict,
        item_key_value: str,
        dep_summaries: dict[str, dict[str, dict]],
        ctx: SkillContext,
        artifacts: dict[str, dict[str, dict]],
    ) -> dict:
        """执行单个展开项: skip_if 过滤 → consume 组装 → SkillRuntime(inline 长超时)"""
        item_state: dict[str, Any] = {"status": "running"}
        # 上游依赖同键项未成功的项不进入本步(失败项不向下游传播; 跳过可追溯)
        for dep in step.depends_on:
            dep_env = (artifacts.get(dep) or {}).get(item_key_value)
            if dep_env is None:
                item_state.update(
                    status="skipped", reason=f"dependency_failed: {dep} 无同键产物"
                )
                return item_state
            if str(dep_env.get("status")) != "succeeded":
                item_state.update(
                    status="skipped", reason=f"dependency_failed: {dep} 未成功"
                )
                return item_state

        # 展开项级过滤 skip_if: 引用 item + 依赖步骤同键项摘要(W-2 降级拦截落点)
        if step.skip_if is not None:
            skip_ctx: dict[str, Any] = {"item": item}
            for dep, per_item in dep_summaries.items():
                skip_ctx[dep] = per_item.get(item_key_value, {})
            try:
                skip_result = bool(evaluate(step.skip_if, skip_ctx))
            except ExprError as e:
                item_state.update(status="failed", error=f"skip_if 表达式非法: {e}")
                return item_state
            item_state["skip_if"] = {"expr": step.skip_if, "result": skip_result}
            if skip_result:
                item_state.update(status="skipped", reason=f"skip_if: {step.skip_if}")
                return item_state

        # 产物传递: consume 声明从依赖步骤同键项的完整产物取字段(内存传递)
        skill_input = {**step.input, **item}
        for field, source in step.consume.items():
            dep_id, _, source_field = source.partition(".")
            dep_env = (artifacts.get(dep_id) or {}).get(item_key_value) or {}
            dep_result = dep_env.get("result") or {}
            skill_input[field] = dep_result.get(source_field)

        # 展开项输入准备器: 执行侧(inline/worker 同进程)物化补充字段(如文档落盘)
        if step.input_resolver:
            try:
                resolver = _load_input_resolver(step.input_resolver)
                extra = dict(await resolver(item, ctx) or {})
            except Exception as e:
                item_state.update(status="failed", error=f"input_resolver 失败: {type(e).__name__}: {e}")
                return item_state
            cleanup = extra.pop("__cleanup_paths", None)
            if cleanup:
                artifacts.setdefault("__cleanup__", []).extend(cleanup)
            skill_input.update(extra)

        skill_manifest = get_skill(step.skill)
        envelope = await self.runtime.invoke(
            step.skill, skill_input, ctx, mode="inline",
            timeout_s=(skill_manifest.execution.queued_timeout_s if skill_manifest else None),
        )
        # 完整产物入内存区供后续步骤 consume(envelope 自身轻量, blocks 在 result)
        artifacts.setdefault(step.id, {})[item_key_value] = envelope

        status = str(envelope.get("status"))
        item_state.update(
            status="succeeded" if status == "succeeded" else "failed",
            invocation_id=envelope.get("invocation_id"),
            degraded=bool(envelope.get("degraded")),
            error=(envelope.get("error") or {}).get("message") if envelope.get("error") else None,
            error_class=(envelope.get("error") or {}).get("class") if envelope.get("error") else None,
        )
        return item_state

    # ################ 观测回写 ################

    @staticmethod
    def _step_summary(step_state: dict) -> dict:
        """步骤聚合摘要(when 表达式引用上下文: 状态+计数)"""
        summary = {"status": step_state.get("status")}
        summary.update(step_state.get("counts") or {})
        return summary

    @staticmethod
    def _item_summary(envelope: dict | None) -> dict:
        """展开项产物摘要(skip_if 表达式引用上下文: status/degraded/error 及标量结果字段)"""
        if not envelope:
            return {"status": "missing"}
        result = envelope.get("result") or {}
        summary = {
            "status": envelope.get("status"),
            "degraded": bool(envelope.get("degraded")),
            "error_class": (envelope.get("error") or {}).get("class"),
        }
        # result 顶层标量字段铺开(如 chunk_count/route), 供表达式引用; 大产物字段排除
        for key, value in result.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = value
        return summary

    async def _load_input(self, job_run_id: str) -> dict:
        """worker resume 时从 input_summary 还原完整 job 输入

        submit 时展开项元数据(file_path 等)已完整存入 input_summary.documents;
        步骤产物(blocks/markdown)不在其中 —— 由各步骤重新产出或经 consume 内存传递。
        """
        async with db_manager.db_rel.session_factory() as session:
            run = await session.get(AgentJobRun, job_run_id)
            if run is None:
                raise ValueError(f"agent_job_run 不存在: {job_run_id}")
            summary = dict(run.input_summary or {})
        return {"documents": summary.get("documents") or [], "project_ids": summary.get("project_ids") or []}

    async def _persist_step(
        self, job_run_id: str, step_id: str, step_state: dict,
        step_artifacts: dict[str, dict] | None = None,
    ) -> None:
        """步骤状态落库(steps_state 增量合并 + 进度汇总 + 产物入 checkpoint, W-3)"""
        async with db_manager.db_rel.session_factory() as session:
            run = await session.get(AgentJobRun, job_run_id)
            if run is None:
                return
            steps_state = dict(run.steps_state or {})
            steps_state[step_id] = step_state
            run.steps_state = steps_state
            # 断点续跑载体: 步骤产物入 checkpoint(下次续跑 consume 依赖)
            if step_artifacts:
                checkpoint = dict(run.checkpoint or {})
                checkpoint_artifacts = dict(checkpoint.get("artifacts") or {})
                checkpoint_artifacts[step_id] = {
                    key: {
                        "invocation_id": env.get("invocation_id"),
                        "status": env.get("status"),
                        "degraded": env.get("degraded"),
                        "result": env.get("result"),
                    }
                    for key, env in step_artifacts.items()
                }
                checkpoint["artifacts"] = checkpoint_artifacts
                run.checkpoint = checkpoint
            # 进度 = 全部已落步骤的项完成数 / 总项数
            total = sum((s.get("counts") or {}).get("total", 0) for s in steps_state.values())
            done = sum(
                (s.get("counts") or {}).get("succeeded", 0)
                + (s.get("counts") or {}).get("failed", 0)
                + (s.get("counts") or {}).get("skipped", 0)
                for s in steps_state.values()
            )
            run.progress = {
                "total": total, "processed": done,
                "percent": round(done * 100.0 / total, 1) if total else 0.0,
            }
            if run.task_id:
                run_row_progress = run.progress
                asyncio.create_task(self._push_task_progress(run.task_id, run_row_progress))
            await session.commit()

    @staticmethod
    async def _push_task_progress(task_id: str, progress: dict) -> None:
        try:
            from module_task.tasks import update_task_fields

            await update_task_fields(
                task_id, progress=progress.get("percent", 0.0),
                message=f"job 进度 {progress.get('processed', 0)}/{progress.get('total', 0)}",
            )
        except Exception as e:  # 进度推送失败不影响 job 执行
            logger.debug("job 进度回写失败(忽略): %s", e)

    async def _finish(
        self, job_run_id: str, status: str, result: dict | None = None, error: str | None = None
    ) -> None:
        async with db_manager.db_rel.session_factory() as session:
            async with session.begin():
                values: dict[str, Any] = {"status": status, "finished_at": datetime.now(timezone.utc)}
                if result is not None:
                    values["result"] = result
                if error is not None:
                    values["error"] = error
                await session.execute(
                    sa_update(AgentJobRun).where(AgentJobRun.job_run_id == job_run_id).values(**values)
                )

    async def _mark(self, job_run_id: str, *, set_started: bool = False, **fields: Any) -> None:
        async with db_manager.db_rel.session_factory() as session:
            async with session.begin():
                values = dict(fields)
                if set_started:
                    values["started_at"] = datetime.now(timezone.utc)
                if values:
                    await session.execute(
                        sa_update(AgentJobRun).where(AgentJobRun.job_run_id == job_run_id).values(**values)
                    )

    async def _merge_checkpoint(self, job_run_id: str, patch: dict) -> None:
        """checkpoint 顶层字段合并写(attempt 等; job 单执行流, 读改写安全)"""
        async with db_manager.db_rel.session_factory() as session:
            run = await session.get(AgentJobRun, job_run_id)
            if run is None:
                return
            checkpoint = dict(run.checkpoint or {})
            checkpoint.update(patch)
            run.checkpoint = checkpoint
            await session.commit()

    async def _find_active_run(self, fingerprint: str) -> AgentJobRun | None:
        from sqlmodel import select

        async with db_manager.db_rel.session_factory() as session:
            rows = await session.exec(
                select(AgentJobRun)
                .where(
                    AgentJobRun.idempotency_key == fingerprint,
                    AgentJobRun.status.in_((JobRunStatus.PENDING, JobRunStatus.RUNNING)),
                )
                .order_by(AgentJobRun.created_at.desc())
                .limit(1)
            )
            return rows.first()

    # ################ 查询 ################

    async def get(self, job_run_id: str) -> AgentJobRun | None:
        async with db_manager.db_rel.session_factory() as session:
            return await session.get(AgentJobRun, job_run_id)
