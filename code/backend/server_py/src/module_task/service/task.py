"""
任务队列服务层

职责:
    - 任务创建: 校验类型注册表 → 落库(pending) → 投递 Redis broker(由 app_task.py worker 消费)
    - 状态检测: 数据库为主, 同时读取结果后端(AsyncResult)做对照/校正
    - 生命周期管理: 取消(revoke)/重试(重新派发)/删除
    - 运维热调: 任务类型入队优先级覆盖(无需改代码/重启)
    - 可观测: Celery 执行器(worker)在线状态采集、手动自愈
"""
import asyncio
from datetime import datetime, timezone

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_task.dao.task import TaskQueueDao
from module_task.do.task import (
    ACTIVE_STATUSES,
    QueueTaskStatus,
    TaskQueue,
    TaskQueueCreate,
    TaskQueueResponse,
    TaskRecoverResponse,
    TaskStatsResponse,
    TaskTypeView,
    WorkerInfo,
    WorkerListResponse,
)
from module_task.tasks import (
    TASK_TYPES,
    dispatch_task,
    fail_stale_running_tasks,
    get_task_type,
    queue_for_priority,
    recover_pending_tasks,
)

# 优先级取值范围(Redis 分级队列 0~9, 数值越大越优先; 越界自动夹紧)
_PRIORITY_MIN, _PRIORITY_MAX = 0, 9


def _clamp_priority(priority: int) -> int:
    """夹紧优先级到 Celery/Redis 支持的 0~9 区间"""
    return max(_PRIORITY_MIN, min(_PRIORITY_MAX, int(priority or 0)))


class TaskNotFoundError(NotFoundError):
    """任务不存在(继承 NotFoundError, 由全局异常处理器映射为 404)"""


# Celery 状态 -> 本模块状态(校正用)
_CELERY_STATE_MAP = {
    "SUCCESS": QueueTaskStatus.SUCCESS,
    "FAILURE": QueueTaskStatus.FAILED,
    "REVOKED": QueueTaskStatus.REVOKED,
}


def _to_response(task: TaskQueue) -> TaskQueueResponse:
    """ORM 转 DTO(纯任务管理: 不透出业务参数/结果, 仅映射执行情况字段)"""
    return TaskQueueResponse(
        id=task.id,
        name=task.name,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status,
        progress=task.progress,
        message=task.message,
        error=task.error,
        celery_task_id=task.celery_task_id,
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _read_celery_state(task: TaskQueue) -> TaskQueueResponse:
    """
    读取 Celery 结果后端的真实状态与百分比, 合并进响应
    (结果后端不可用时静默降级: celery 字段保持 None, 不影响主流程)
    """
    resp = _to_response(task)
    if not task.celery_task_id:
        return resp
    try:
        # celery 实例惰性获取(避免 Web 进程启动即加载 celery)
        from common.config.tasks import app as celery_app

        async_result = celery_app.AsyncResult(task.celery_task_id)
        # state/info/result 每次访问都是一次结果后端(Redis)往返,
        # 只取一次 state, 其余按需读取(列表页每行都会走本函数)
        state = async_result.state
        resp.celery_state = state
        # PROGRESS 状态下 info 为 worker update_state 写入的 meta
        if state == "PROGRESS" and isinstance(async_result.info, dict):
            resp.celery_meta = dict(async_result.info)
            resp.celery_progress = async_result.info.get("progress")
        elif state == "FAILURE":
            resp.error = resp.error or str(async_result.result)
    except Exception:
        pass
    return resp


class TaskQueueService:
    def __init__(self, dao: TaskQueueDao):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.dao = dao

    # ################ 查询 ################

    async def list_page(
        self,
        pagination: PaginationParams,
        keyword: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        priority: int | None = None,
    ) -> PaginationResponse:
        """分页查询任务列表(列表项附带 Celery 状态对照)"""
        items = await self.dao.list_page(
            pagination,
            keyword=keyword,
            status=status,
            task_type=task_type,
            priority=priority,
        )
        total = await self.dao.count(
            keyword=keyword, status=status, task_type=task_type, priority=priority,
        )
        return PaginationResponse.create(
            [_read_celery_state(t) for t in items], total, pagination,
        )

    async def get(self, task_id: str) -> TaskQueueResponse:
        """
        查询任务详情(含 Celery 侧状态/百分比)
        :raises ValueError: 任务不存在
        """
        task = await self.dao.get(task_id)
        if not task:
            raise NotFoundError(f"未找到ID为 {task_id} 的任务")
        return _read_celery_state(task)

    async def stats(self) -> TaskStatsResponse:
        """按状态统计任务数(概览卡片/轮询)"""
        raw = await self.dao.stats()
        return TaskStatsResponse(
            total=sum(raw.values()),
            pending=raw.get(QueueTaskStatus.PENDING, 0),
            running=raw.get(QueueTaskStatus.RUNNING, 0),
            success=raw.get(QueueTaskStatus.SUCCESS, 0),
            failed=raw.get(QueueTaskStatus.FAILED, 0),
            cancelled=raw.get(QueueTaskStatus.CANCELLED, 0)
            + raw.get(QueueTaskStatus.REVOKED, 0),
        )

    async def registry(self) -> list[TaskTypeView]:
        """任务类型注册表(合并 DB 优先级覆盖, 供前端渲染下拉与优先级热调表)"""
        overrides = await self.dao.get_all_priority_overrides()
        views: list[TaskTypeView] = []
        for t in TASK_TYPES.values():
            override = overrides.get(t.type)
            effective = _clamp_priority(
                t.default_priority if override is None else override
            )
            views.append(
                TaskTypeView(
                    type=t.type,
                    name=t.name,
                    description=t.description,
                    celery_task=t.celery_task,
                    default_payload=t.default_payload,
                    default_priority=t.default_priority,
                    priority_override=override,
                    effective_priority=effective,
                    queue=queue_for_priority(effective),
                )
            )
        return views

    async def set_type_priority(
        self, task_type: str, priority: int | None
    ) -> TaskTypeView:
        """
        热调某任务类型的入队优先级(运维操作, 立即对之后创建的任务生效)
        :param priority: 0~9; 传 None 表示清除覆盖, 回落注册表默认优先级
        :raises NotFoundError: 任务类型未在注册表登记
        """
        if get_task_type(task_type) is None:
            raise NotFoundError(f"任务类型 {task_type} 未在注册表登记")
        if priority is None:
            await self.dao.delete_priority_override(task_type)
        else:
            await self.dao.upsert_priority_override(
                task_type, _clamp_priority(priority)
            )
        views = {v.type: v for v in await self.registry()}
        return views[task_type]

    async def workers(self) -> WorkerListResponse:
        """
        采集 Celery 执行器(worker)在线状态(控制 ping/stats/active 队列)

        inspect 为同步阻塞调用, 放线程池执行; broker/worker 不可用时
        返回 online=0 + error 提示而非抛异常, 便于前端展示"全部离线"。
        """
        def _inspect() -> WorkerListResponse:
            from common.config.tasks import app as celery_app

            try:
                insp = celery_app.control.inspect(timeout=1.5)
                pings = insp.ping() or {}
                if not pings:
                    return WorkerListResponse(
                        total=0, online=0, error="没有执行器响应(可能均未启动)"
                    )
                stats = insp.stats() or {}
                active_queues = insp.active_queues() or {}
                active_tasks = insp.active() or {}
            except Exception as exc:  # broker 不可达等
                return WorkerListResponse(error=f"执行器状态采集失败: {exc}")

            workers: list[WorkerInfo] = []
            for name, pong in pings.items():
                if not (isinstance(pong, dict) and pong.get("ok") == "pong"):
                    continue
                st = stats.get(name) or {}
                pool = st.get("pool", {}) or {}
                queues = sorted(
                    {
                        q.get("name")
                        for q in (active_queues.get(name) or [])
                        if q.get("name")
                    }
                )
                running = [
                    {
                        "name": t.get("name", ""),
                        "id": t.get("id", ""),
                        "args": str(t.get("args", ""))[:200],
                    }
                    for t in (active_tasks.get(name) or [])
                ]
                workers.append(
                    WorkerInfo(
                        name=name,
                        queues=queues,
                        concurrency=int(pool.get("max-concurrency") or 0),
                        active=len(running),
                        processed=int(
                            (st.get("total") or {}).get(
                                "tasks", st.get("processed") or 0
                            )
                        ),
                        uptime_seconds=None,
                        active_tasks=running,
                        pid=st.get("pid"),
                    )
                )
            return WorkerListResponse(
                total=len(workers), online=len(workers), workers=workers
            )

        return await asyncio.to_thread(_inspect)

    async def recover(self) -> TaskRecoverResponse:
        """
        手动触发任务自愈(重启残留 PENDING 重派发 + 僵尸 RUNNING 归档失败)

        语义与 app_task.py 启动自愈/Reaper 周期清扫一致, 用于运维即时干预。
        """
        recovered = await recover_pending_tasks()
        reaped = await fail_stale_running_tasks()
        return TaskRecoverResponse(recovered=recovered, reaped=reaped)

    # ################ 创建/投递 ################

    async def create(self, data: TaskQueueCreate, user_id: str) -> TaskQueueResponse:
        """
        创建任务并投递 broker(由 app_task.py worker 异步执行)
        :param data: 任务数据(类型需在注册表内)
        :param user_id: 创建者用户ID
        :raises BusinessError: 类型未注册 / 派发不可用
        """
        task_def = get_task_type(data.task_type)
        if task_def is None:
            registered = ", ".join(TASK_TYPES.keys())
            raise BusinessError(
                f"任务类型 {data.task_type} 未注册(可用类型: {registered})"
            )

        # 优先级解析: 显式传入 > 类型覆盖(DB 热调) > 类型注册表默认
        if data.priority is None:
            overrides = await self.dao.get_all_priority_overrides()
            override = overrides.get(data.task_type)
            effective = task_def.default_priority if override is None else override
        else:
            effective = data.priority

        task = TaskQueue(
            name=data.name,
            task_type=data.task_type,
            payload=data.payload or {},
            priority=_clamp_priority(effective),
            user_id=user_id,
            status=QueueTaskStatus.PENDING,
        )
        await self.dao.add(task)

        # 统一派发(仅传任务ID, 参数由执行侧从库中读取)
        try:
            task.celery_task_id = await dispatch_task(task, task_def)
            await self.dao.update(task)
        except Exception as exc:
            # 派发不可用: 标记失败并保留记录, 前端可见失败原因
            task.status = QueueTaskStatus.FAILED
            task.error = f"任务派发失败: {exc}"
            task.finished_at = datetime.now(timezone.utc)
            await self.dao.update(task)
            raise BusinessError(
                f"任务派发失败, 请检查任务配置(Redis broker 与 worker): {exc}"
            ) from exc
        return _to_response(task)

    # ################ 状态同步 ################

    async def sync_from_celery(self, task_id: str) -> TaskQueueResponse:
        """
        以 Celery 结果后端为准校正数据库状态(用于 worker 回写中断等异常场景)
        仅在数据库为非终态时校正, 不覆盖已确认的终态。
        """
        task = await self.dao.get(task_id)
        if not task:
            raise NotFoundError(f"未找到ID为 {task_id} 的任务")

        if task.status in ACTIVE_STATUSES and task.celery_task_id:
            try:
                from common.config.tasks import app as celery_app

                async_result = celery_app.AsyncResult(task.celery_task_id)
                mapped = _CELERY_STATE_MAP.get(async_result.state)
                if mapped == QueueTaskStatus.SUCCESS:
                    task.status = QueueTaskStatus.SUCCESS
                    task.progress = 100
                    task.message = "处理完成(由结果后端同步)"
                    if isinstance(async_result.result, dict):
                        task.result = async_result.result
                    task.finished_at = datetime.now(timezone.utc)
                    await self.dao.update(task)
                elif mapped in (QueueTaskStatus.FAILED, QueueTaskStatus.REVOKED):
                    task.status = mapped
                    task.error = str(async_result.result) if mapped == QueueTaskStatus.FAILED else "已被撤销(由结果后端同步)"
                    task.finished_at = datetime.now(timezone.utc)
                    await self.dao.update(task)
            except Exception:
                pass  # 结果后端不可用时跳过校正
        return _read_celery_state(task)

    # ################ 生命周期 ################

    async def cancel(self, task_id: str) -> None:
        """
        取消任务(非终态才可取消): Celery revoke + 数据库置 cancelled
        :raises ValueError: 任务不存在或已处于终态
        """
        task = await self.dao.get(task_id)
        if not task:
            raise TaskNotFoundError(f"未找到ID为 {task_id} 的任务")
        if task.status not in ACTIVE_STATUSES:
            raise BusinessError(f"任务已结束({task.status}), 无法取消")

        # 先撤销 Celery 侧(排队中直接丢弃; 执行中由 worker 协作式检查提前退出)
        if task.celery_task_id:
            try:
                from common.config.tasks import app as celery_app

                celery_app.control.revoke(task.celery_task_id, terminate=True)
            except Exception:
                pass  # 撤销失败不阻塞本地取消(worker 仍会检查库中状态)
        task.status = QueueTaskStatus.CANCELLED
        task.message = "任务已取消"
        task.finished_at = datetime.now(timezone.utc)
        await self.dao.update(task)

    async def retry(self, task_id: str) -> TaskQueueResponse:
        """
        重试任务(仅终态任务): 重置状态后按引擎重新派发
        :raises ValueError: 任务不存在/未结束/类型未注册
        """
        task = await self.dao.get(task_id)
        if not task:
            raise TaskNotFoundError(f"未找到ID为 {task_id} 的任务")
        if task.status in ACTIVE_STATUSES:
            raise BusinessError("任务仍在进行中, 无需重试")

        task_def = get_task_type(task.task_type)
        if task_def is None:
            raise BusinessError(f"任务类型 {task.task_type} 已从注册表移除, 无法重试")

        task.status = QueueTaskStatus.PENDING
        task.progress = 0
        task.message = None
        task.result = None
        task.error = None
        task.finished_at = None
        task.celery_task_id = None
        try:
            task.celery_task_id = await dispatch_task(task, task_def)
        except Exception as exc:
            task.status = QueueTaskStatus.FAILED
            task.error = f"任务派发失败: {exc}"
            task.finished_at = datetime.now(timezone.utc)
            await self.dao.update(task)
            raise BusinessError(
                f"任务派发失败, 请检查任务配置"
                f"(celery 引擎需检查 Redis 与 worker): {exc}"
            ) from exc
        await self.dao.update(task)
        return _to_response(task)

    async def delete(self, task_id: str) -> None:
        """删除任务记录(任何状态均可删除)"""
        await self.dao.delete(task_id)
