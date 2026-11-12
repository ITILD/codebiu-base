"""SkillRuntime: 三入口汇合的统一技能运行时(REQ-018, 设计 §3.2/§4)

Web Controller / Agent Tool Adapter / Task Executor(Celery) 三条入口全部汇合于
SkillRuntime.invoke() —— 同一 Skill 一份实现两种外壳(inline/queued, CA-04):

职责边界:
- 模式决策(auto): Skill 声明 + 输入规模 + priority_class 决定 inline/queued(§4.2)
- 能力解析: required 缺失快速失败(capability_missing); alternatives 选组(W-6);
  optional 缺失降级(degraded=true)
- inline 硬超时(CA-05); queued 先落 task_queue 再投 Celery(CA-10)
- 全部调用写 skill_invocation, 失败带 error_class(CA-11)
- impl 契约: async run(input: dict, ctx: SkillContext, caps: CapabilityResolution,
  progress: ProgressFn) -> dict —— 实现保持薄, 编排 Service 调用
"""

import asyncio
import hashlib
import importlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import select

from common.config.db import db_manager
from module_agent.do.skill import InvocationStatus, SkillInvocation
from module_agent.skills.manifest import SkillManifest
from module_agent.skills.registry import get_skill, require_skill

logger = logging.getLogger(__name__)

# 进度回调: (percent 0~100, message) -> None
ProgressFn = Callable[[float, str], Awaitable[None]]


class SkillContext(BaseModel):
    """技能执行上下文(资源授权范围载体, CA-08: user_id/project_ids 由运行时注入)"""

    user_id: str = Field(description="调用者用户ID(底层服务按其解析模型/权限)")
    project_ids: list[str] = Field(default_factory=list, description="授权项目范围(仅过滤用, 不可扩大)")
    conversation_id: str | None = Field(default=None, description="会话ID(对话入口)")
    priority_class: str = Field(default="standard", description="interactive/standard/batch(服务端判定)")
    deadline_s: float | None = Field(default=None, description="软截止(秒, 超时应降级而非硬失败)")
    trace_id: str | None = Field(default=None, description="链路追踪ID")
    entry: str = Field(default="web", description="触发入口: web/agent/task/debug")


class CapabilityMissingError(Exception):
    """必需能力不可满足(不重试, 发布/运行前拦截, §3.4)"""

    def __init__(self, message: str):
        super().__init__(message)
        self.error_class = "capability_missing"


class CapabilityResolution(BaseModel):
    """一次调用的能力解析结果(降级依据)"""

    required: dict[str, dict[str, Any]] = Field(default_factory=dict, description="必需能力 → 解析结果")
    optional: dict[str, dict[str, Any]] = Field(default_factory=dict, description="可选能力 → 解析结果")
    missing_optional: list[str] = Field(default_factory=list, description="缺失的可选能力(降级原因)")
    selected_group: list[str] | None = Field(default=None, description="选中的能力组(首选组=完整路线)")
    degraded: bool = Field(default=False, description="是否降级完成")

    def group_satisfies(self, capability_key: str) -> bool:
        """选中组是否包含指定能力(impl 判定执行路线用)"""
        return bool(self.selected_group) and capability_key in self.selected_group


def classify_error(exc: Exception) -> str:
    """异常 → error_class(§3.4 失败语义: 每类的重试/呈现策略固定)"""
    import httpx
    from pydantic import ValidationError

    if isinstance(exc, CapabilityMissingError):
        return "capability_missing"
    if isinstance(exc, ValidationError):
        return "invalid_input"
    if isinstance(exc, asyncio.TimeoutError):
        return "transient"  # inline 超时可重试(建议转 queued), 不自动转(避免重复副作用)
    if isinstance(exc, (httpx.HTTPError, ConnectionError, TimeoutError)):
        return "transient"
    if isinstance(exc, ValueError):
        return "invalid_input"
    return "permanent"


def _storage_sanitize(value: Any, max_str: int = 8000) -> Any:
    """观测存储清洗: 递归截断超长字符串(完整产物只在调用返回值/编排内存中流转)"""
    if isinstance(value, str):
        return value if len(value) <= max_str else value[:max_str] + f"...[截断, 原长 {len(value)}]"
    if isinstance(value, dict):
        return {k: _storage_sanitize(v, max_str) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_storage_sanitize(v, max_str) for v in value]
    return value


_impl_cache: dict[str, Callable[..., Awaitable[dict]]] = {}


def load_impl(manifest: SkillManifest) -> Callable[..., Awaitable[dict]]:
    """按 impl_ref 动态加载实现函数('模块路径:函数名', 带进程内缓存)"""
    cached = _impl_cache.get(manifest.impl_ref)
    if cached is not None:
        return cached
    module_path, _, func_name = manifest.impl_ref.partition(":")
    if not module_path or not func_name:
        raise ValueError(f"impl_ref 非法(应为 '模块路径:函数名'): {manifest.impl_ref}")
    module = importlib.import_module(module_path)
    fn = getattr(module, func_name)
    if not asyncio.iscoroutinefunction(fn):
        raise ValueError(f"Skill 实现必须是协程函数: {manifest.impl_ref}")
    _impl_cache[manifest.impl_ref] = fn
    return fn


class SkillRuntime:
    """统一技能运行时(进程内单例语义, 无状态)"""

    # ################ 能力解析 ################

    @staticmethod
    async def resolve_capabilities(
        manifest: SkillManifest, ctx: SkillContext
    ) -> CapabilityResolution:
        """解析 Skill 声明的全部能力(required/optional/alternatives, 设计 §3.1)

        :raises CapabilityMissingError: required 缺失或 alternatives 全组不可满足
        """
        from module_ai.service.capability_registry import resolve as resolve_capability

        async def _resolve(key: str) -> dict[str, Any]:
            r = await resolve_capability(key, ctx.user_id)
            return r.model_dump()

        required = {k: await _resolve(k) for k in manifest.required_capabilities}
        missing_required = [k for k, r in required.items() if not r["available"]]
        if missing_required:
            raise CapabilityMissingError(
                f"必需能力不可满足: {', '.join(missing_required)}"
                f"(Skill {manifest.uid}, 请在模型管理/能力注册中配置)"
            )

        optional = {k: await _resolve(k) for k in manifest.optional_capabilities}
        missing_optional = [k for k, r in optional.items() if not r["available"]]

        selected_group: list[str] | None = None
        if manifest.capability_alternatives:
            for group in manifest.capability_alternatives:
                resolved = [await _resolve(k) for k in group]
                if all(r["available"] for r in resolved):
                    selected_group = list(group)
                    break
            if selected_group is None:
                keys = " / ".join("|".join(g) for g in manifest.capability_alternatives)
                raise CapabilityMissingError(
                    f"能力组全部不可满足: {keys}(Skill {manifest.uid})"
                )
            degraded = selected_group != list(manifest.capability_alternatives[0])
        else:
            degraded = False

        return CapabilityResolution(
            required=required,
            optional=optional,
            missing_optional=missing_optional,
            selected_group=selected_group,
            degraded=degraded or bool(missing_optional),
        )

    # ################ 模式决策 ################

    @staticmethod
    def decide_mode(manifest: SkillManifest, skill_input: dict, ctx: SkillContext, mode: str) -> str:
        """执行形态决策(§4.2): 声明优先 → batch 类 → 输入规模 → inline"""
        if mode in ("inline", "queued"):
            if mode not in manifest.execution.modes:
                raise ValueError(f"Skill {manifest.uid} 不支持 {mode} 形态(声明: {manifest.execution.modes})")
            return mode
        modes = manifest.execution.modes
        if "queued" not in modes:
            return "inline"
        if "inline" not in modes:
            return "queued"
        if ctx.priority_class == "batch":
            return "queued"
        size_hint = skill_input.get("size_hint") or 0
        threshold = manifest.execution.inline_max_input_bytes
        if threshold is not None and isinstance(size_hint, (int, float)) and size_hint > threshold:
            return "queued"
        return "inline"

    # ################ 幂等 ################

    @staticmethod
    def _idempotency_fingerprint(manifest: SkillManifest, skill_input: dict) -> str | None:
        """按声明的 idempotency.keys 拼装指纹(CA-03; 未声明 keys 返回 None 不去重)"""
        keys = manifest.idempotency.keys
        if not keys:
            return None
        payload = json.dumps(
            [manifest.uid, manifest.version] + [skill_input.get(k) for k in keys],
            ensure_ascii=False, sort_keys=True, default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    # ################ 主入口 ################

    async def invoke(
        self,
        skill_key: str,
        skill_input: dict,
        ctx: SkillContext,
        mode: str = "auto",
        timeout_s: float | None = None,
    ) -> dict:
        """统一调用入口(§3.2 契约; 永不抛业务异常, 结果一律走统一信封)

        :param timeout_s: 覆盖 inline 硬超时(仍为硬超时, CA-05;
            job 编排在 worker 内以 inline 长超时直接执行步骤, 避免嵌套排队死锁)
        :return: {invocation_id, skill_key, mode, status, task_id, result, error, progress, degraded}
        """
        try:
            manifest = require_skill(skill_key)
        except Exception as e:
            return self._envelope_error(skill_key, "invalid_input", str(e))

        fingerprint = self._idempotency_fingerprint(manifest, skill_input)
        if fingerprint is not None:
            reused = await self._find_reusable(manifest.uid, fingerprint)
            if reused is not None:
                logger.info("Skill 调用幂等复用: %s -> %s", manifest.uid, reused.invocation_id)
                return self._envelope(manifest, reused, result=reused.output, progress=100)

        try:
            caps = await self.resolve_capabilities(manifest, ctx)
        except CapabilityMissingError as e:
            invocation = await self._create_invocation(
                manifest, ctx, mode="inline", status=InvocationStatus.FAILED,
                fingerprint=fingerprint, input_summary=self._input_summary(manifest, skill_input),
                error_class="capability_missing", error_message=str(e),
            )
            return self._envelope(manifest, invocation, error={"class": "capability_missing", "message": str(e)})

        chosen_mode = self.decide_mode(manifest, skill_input, ctx, mode)
        if chosen_mode == "queued":
            return await self._invoke_queued(manifest, skill_input, ctx, caps, fingerprint)
        return await self._invoke_inline(manifest, skill_input, ctx, caps, fingerprint, timeout_s)

    # ################ 执行体 ################

    async def _execute_body(
        self,
        manifest: SkillManifest,
        skill_input: dict,
        ctx: SkillContext,
        caps: CapabilityResolution,
        progress_sink: ProgressFn | None = None,
    ) -> dict:
        """执行 Skill 实现体(CA-04: inline/queued 共用同一实现)"""

        async def _progress(percent: float, message: str) -> None:
            if progress_sink is not None:
                try:
                    await progress_sink(float(percent), message)
                except Exception as e:  # 进度失败不影响执行
                    logger.debug("进度回调失败(忽略): %s", e)

        impl = load_impl(manifest)
        result = await impl(skill_input, ctx, caps, _progress)
        if not isinstance(result, dict):
            raise ValueError(
                f"Skill 实现返回值必须是 dict(output_schema 契约), 实际: {type(result).__name__}"
            )
        return result

    async def _invoke_inline(
        self,
        manifest: SkillManifest,
        skill_input: dict,
        ctx: SkillContext,
        caps: CapabilityResolution,
        fingerprint: str | None,
        timeout_s: float | None = None,
    ) -> dict:
        """inline 执行: 进程内 + 硬超时(CA-05); 超时不自动转 queued(避免重复副作用)"""
        invocation = await self._create_invocation(
            manifest, ctx, mode="inline", fingerprint=fingerprint,
            input_summary=self._input_summary(manifest, skill_input),
        )
        await self._mark(invocation.invocation_id, status=InvocationStatus.RUNNING, set_started=True)
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._execute_body(manifest, skill_input, ctx, caps),
                timeout=timeout_s or manifest.execution.inline_timeout_s,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            await self._mark(
                invocation.invocation_id,
                status=InvocationStatus.SUCCEEDED,
                output=_storage_sanitize(result),
                degraded=caps.degraded,
                duration_ms=duration_ms,
                tokens=int(result.get("meta", {}).get("tokens", 0) or 0)
                if isinstance(result.get("meta"), dict) else 0,
                set_finished=True,
            )
            return self._envelope(
                manifest, invocation, mode="inline", status="succeeded",
                result=result, degraded=caps.degraded, progress=100,
            )
        except Exception as e:
            error_class = classify_error(e)
            message = f"{type(e).__name__}: {e}"
            hint = (
                " (inline 超时, 可重试; 长任务建议 mode=queued)"
                if isinstance(e, asyncio.TimeoutError) else ""
            )
            await self._mark(
                invocation.invocation_id,
                status=InvocationStatus.FAILED,
                error_class=error_class,
                error_message=message[:1000],
                duration_ms=int((time.monotonic() - started) * 1000),
                set_finished=True,
            )
            logger.warning("Skill inline 执行失败 %s: %s", manifest.uid, message)
            return self._envelope(
                manifest, invocation, mode="inline", status="failed",
                error={"class": error_class, "message": message + hint},
            )

    async def _invoke_queued(
        self,
        manifest: SkillManifest,
        skill_input: dict,
        ctx: SkillContext,
        caps: CapabilityResolution,
        fingerprint: str | None,
    ) -> dict:
        """queued 执行: 先落 skill_invocation(pending) → 落 task_queue → 投 Celery(CA-10)"""
        from module_task.dao.task import TaskQueueDao
        from module_task.do.task import TaskQueue, TaskQueueCreate
        from module_task.service.task import TaskQueueService

        invocation = await self._create_invocation(
            manifest, ctx, mode="queued", status=InvocationStatus.PENDING,
            fingerprint=fingerprint, input_summary=self._input_summary(manifest, skill_input),
        )
        priority = {"interactive": 7, "standard": 5, "batch": 2}.get(ctx.priority_class, 5)
        try:
            task = await TaskQueueService(TaskQueueDao()).create(
                TaskQueueCreate(
                    name=f"Skill: {manifest.name}({manifest.uid})",
                    task_type="skill_execute",
                    payload={
                        "invocation_id": invocation.invocation_id,
                        "skill_key": manifest.uid,
                        "skill_input": skill_input,
                    },
                    priority=priority,
                ),
                ctx.user_id,
            )
        except Exception as e:
            message = f"任务投递失败: {e}"
            await self._mark(
                invocation.invocation_id, status=InvocationStatus.FAILED,
                error_class="transient", error_message=message[:1000], set_finished=True,
            )
            return self._envelope(
                manifest, invocation, mode="queued", status="failed",
                error={"class": "transient", "message": message},
            )

        # 双向关联: task_queue.invocation_id ↔ skill_invocation.task_id
        async with db_manager.db_rel.session_factory() as session:
            task_row = await session.get(TaskQueue, task.id)
            if task_row is not None:
                task_row.invocation_id = invocation.invocation_id
            invocation_row = await session.get(SkillInvocation, invocation.invocation_id)
            if invocation_row is not None:
                invocation_row.task_id = task.id
            await session.commit()

        return self._envelope(
            manifest, invocation, mode="queued", status="pending",
            task_id=task.id, degraded=caps.degraded,
        )

    # ################ queued worker 侧入口 ################

    async def execute_queued(self, invocation_id: str, task_id: str) -> dict:
        """Task Executor 回调入口: worker 领取任务后经此回到同一运行时(入口③)"""
        from module_task.tasks import update_task_fields

        async with db_manager.db_rel.session_factory() as session:
            invocation = await session.get(SkillInvocation, invocation_id)
            if invocation is None:
                raise ValueError(f"skill_invocation 不存在: {invocation_id}")
            if invocation.status != InvocationStatus.PENDING:
                logger.info("调用已处理过(幂等跳过): %s status=%s", invocation_id, invocation.status)
                return self._envelope_from_row(invocation)
            # ORM 属性在 session 关闭前取到本地变量(detached 后不再触发惰性加载)
            skill_key = invocation.skill_key
            payload_input = dict(invocation.input_summary.get("__raw_input") or {})
            run_user_id = invocation.user_id
            run_priority = invocation.priority_class
            run_trace = invocation.trace_id

        manifest = get_skill(skill_key)
        if manifest is None:
            await self._mark(
                invocation_id, status=InvocationStatus.FAILED,
                error_class="permanent", error_message=f"Skill 已下线: {skill_key}",
                set_finished=True,
            )
            await update_task_fields(
                task_id, status="failed", error=f"Skill 已下线: {skill_key}", set_finished=True
            )
            raise ValueError(f"Skill 已下线: {skill_key}")

        ctx = SkillContext(
            user_id=run_user_id,
            priority_class=run_priority,
            entry="task",
            trace_id=run_trace,
        )

        await self._mark(invocation_id, status=InvocationStatus.RUNNING, set_started=True)

        async def _progress(percent: float, message: str) -> None:
            await update_task_fields(task_id, progress=percent, message=message)

        started = time.monotonic()
        try:
            caps = await self.resolve_capabilities(manifest, ctx)
            result = await asyncio.wait_for(
                self._execute_body(manifest, payload_input, ctx, caps, _progress),
                timeout=manifest.execution.queued_timeout_s,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            await self._mark(
                invocation_id,
                status=InvocationStatus.SUCCEEDED,
                output=_storage_sanitize(result),
                degraded=caps.degraded,
                duration_ms=duration_ms,
                set_finished=True,
            )
            await update_task_fields(
                task_id, status="success", progress=100, message="执行完成",
                result={"invocation_id": invocation_id, "degraded": caps.degraded},
                set_finished=True,
            )
            return {
                "invocation_id": invocation_id, "skill_key": skill_key, "mode": "queued",
                "status": "succeeded", "task_id": task_id, "result": result,
                "error": None, "progress": 100, "degraded": caps.degraded,
            }
        except Exception as e:
            error_class = classify_error(e)
            message = f"{type(e).__name__}: {e}"
            await self._mark(
                invocation_id,
                status=InvocationStatus.FAILED,
                error_class=error_class, error_message=message[:1000],
                duration_ms=int((time.monotonic() - started) * 1000),
                set_finished=True,
            )
            await update_task_fields(
                task_id, status="failed", error=message[:1000], set_finished=True
            )
            logger.warning("Skill queued 执行失败 %s: %s", skill_key, message)
            return {
                "invocation_id": invocation_id, "skill_key": skill_key, "mode": "queued",
                "status": "failed", "task_id": task_id, "result": None,
                "error": {"class": error_class, "message": message}, "progress": 0,
                "degraded": False,
            }

    # ################ 查询 ################

    async def get_invocation(self, invocation_id: str) -> SkillInvocation | None:
        async with db_manager.db_rel.session_factory() as session:
            return await session.get(SkillInvocation, invocation_id)

    # ################ 内部: 观测落库 ################

    @staticmethod
    def _input_summary(manifest: SkillManifest, skill_input: dict) -> dict:
        """输入摘要: 幂等键字段原文 + 完整输入(queued worker 取回用, 截断保护)"""
        return {
            "idempotency_fields": {
                k: skill_input.get(k) for k in manifest.idempotency.keys
            },
            "size_hint": skill_input.get("size_hint"),
            "__raw_input": _storage_sanitize(skill_input),
        }

    async def _create_invocation(
        self,
        manifest: SkillManifest,
        ctx: SkillContext,
        *,
        mode: str,
        fingerprint: str | None,
        input_summary: dict,
        status: str = InvocationStatus.PENDING,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> SkillInvocation:
        row = SkillInvocation(
            skill_key=manifest.uid,
            skill_version=manifest.version,
            mode=mode,
            status=status,
            priority_class=ctx.priority_class,
            idempotency_key=fingerprint,
            input_summary=input_summary,
            degraded=False,
            error_class=error_class,
            error_message=error_message,
            entry=ctx.entry,
            user_id=ctx.user_id,
            trace_id=ctx.trace_id,
        )
        if status == InvocationStatus.FAILED:
            row.started_at = row.finished_at = row.created_at
        async with db_manager.db_rel.session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    @staticmethod
    async def _mark(
        invocation_id: str, *, set_started: bool = False, set_finished: bool = False, **fields: Any
    ) -> None:
        """回写调用观测(终态字段/耗时/降级标记等)"""
        from datetime import datetime, timezone

        from sqlalchemy import update

        allowed = {
            "status", "output", "degraded", "error_class", "error_message",
            "duration_ms", "tokens", "task_id",
        }
        values = {k: v for k, v in fields.items() if k in allowed}
        if "degraded" in fields:
            values["degraded"] = bool(fields["degraded"])
        now = datetime.now(timezone.utc)
        if set_started:
            values["started_at"] = now
        if set_finished:
            values["finished_at"] = now
        if not values:
            return
        async with db_manager.db_rel.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(SkillInvocation)
                    .where(SkillInvocation.invocation_id == invocation_id)
                    .values(**values)
                )

    async def _find_reusable(self, skill_key: str, fingerprint: str) -> SkillInvocation | None:
        """幂等复用: 同指纹且**进行中**(pending/running)的调用 —— 防重复并发提交;
        已成功的不复用(保留「重新解析=幂等重跑」语义, 设计 §5.1)"""
        async with db_manager.db_rel.session_factory() as session:
            rows = await session.exec(
                select(SkillInvocation)
                .where(
                    SkillInvocation.skill_key == skill_key,
                    SkillInvocation.idempotency_key == fingerprint,
                    SkillInvocation.status.in_(
                        (InvocationStatus.PENDING, InvocationStatus.RUNNING)
                    ),
                )
                .order_by(SkillInvocation.created_at.desc())
                .limit(1)
            )
            return rows.first()

    # ################ 信封 ################

    @staticmethod
    def _envelope(
        manifest: SkillManifest | None,
        invocation: SkillInvocation,
        *,
        mode: str | None = None,
        status: str | None = None,
        task_id: str | None = None,
        result: dict | None = None,
        error: dict | None = None,
        degraded: bool = False,
        progress: float = 0,
    ) -> dict:
        """统一返回信封(§3.2)"""
        return {
            "invocation_id": invocation.invocation_id,
            "skill_key": invocation.skill_key if manifest is None else manifest.uid,
            "mode": mode or invocation.mode,
            "status": status or invocation.status,
            "task_id": task_id or invocation.task_id,
            "result": result,
            "error": error,
            "progress": progress,
            "degraded": degraded,
        }

    @classmethod
    def _envelope_from_row(cls, invocation: SkillInvocation) -> dict:
        return {
            "invocation_id": invocation.invocation_id,
            "skill_key": invocation.skill_key,
            "mode": invocation.mode,
            "status": invocation.status,
            "task_id": invocation.task_id,
            "result": invocation.output,
            "error": (
                {"class": invocation.error_class, "message": invocation.error_message}
                if invocation.error_class else None
            ),
            "progress": 100 if invocation.status == InvocationStatus.SUCCEEDED else 0,
            "degraded": invocation.degraded,
        }

    @staticmethod
    def _envelope_error(skill_key: str, error_class: str, message: str) -> dict:
        """未进入执行体的失败(Skill 不存在等)"""
        return {
            "invocation_id": None,
            "skill_key": skill_key,
            "mode": None,
            "status": "failed",
            "task_id": None,
            "result": None,
            "error": {"class": error_class, "message": message},
            "progress": 0,
            "degraded": False,
        }
