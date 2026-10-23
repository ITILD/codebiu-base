"""
周期调度服务层(REQ-012)

职责:
    - 调度定义 CRUD: 校验类型注册表/触发方式(cron 或 interval 二选一) → 落库
    - 下次触发时刻计算: 创建/启停/改周期时重算并唤醒 local 调度循环(热生效)
    - tick 扫描派发: 查到期调度 → 复用任务队列创建/派发链路(local/celery 双引擎)
      → 回写最近一次执行快照; 完整执行历史即 task_queue 记录

内存与体积约束(REQ-012 交付要求):
    - 无常驻调度缓存: tick 只查到期行(复合索引, 单轮 limit 20), 触发后即释放
    - 执行历史不建关联表: 仅回写 last_task_id/last_status 快照, 防 task_schedule 膨胀
"""
import logging
from datetime import datetime, timedelta, timezone

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_task.dao.schedule import TaskScheduleDao
from module_task.do.schedule import (
    MIN_INTERVAL_SECONDS,
    TaskSchedule,
    TaskScheduleCreate,
    TaskScheduleResponse,
    TaskScheduleTriggerResult,
    TaskScheduleUpdate,
)
from module_task.do.task import TaskQueueCreate
from module_task.service.task import TaskQueueService
from module_task.tasks import TASK_TYPES, get_task_type
from module_task.utils.cron import CronError, next_fire

logger = logging.getLogger(__name__)

# 单轮 tick 最多触发数(与 dao.due_schedules limit 一致, 大量到期时分轮推进)
TICK_BATCH = 20


def _validate_definition(task_type: str, cron: str | None, interval_seconds: int | None) -> None:
    """校验任务类型已注册 + 触发方式二选一(cron 语法在重算时校验)"""
    if get_task_type(task_type) is None:
        registered = ", ".join(TASK_TYPES.keys())
        raise BusinessError(f"任务类型 {task_type} 未注册(可用类型: {registered})")
    if cron and interval_seconds:
        raise BusinessError("cron 与 interval_seconds 只能二选一")
    if not cron and not interval_seconds:
        raise BusinessError("须提供 cron 表达式或 interval_seconds 之一")
    if interval_seconds is not None and interval_seconds < MIN_INTERVAL_SECONDS:
        raise BusinessError(f"interval_seconds 不得小于 {MIN_INTERVAL_SECONDS} 秒(分钟级调度)")


def compute_next_fire(
    cron: str | None, interval_seconds: int | None, base: datetime
) -> datetime:
    """
    计算下次触发时刻
    :param base: 计算基准(启用/创建时为当前时刻; 触发推进时为本次 next_fire_at, 防累积漂移)
    :raises BusinessError: cron 语法非法或无可命中时刻
    """
    if interval_seconds:
        return base + timedelta(seconds=interval_seconds)
    try:
        return next_fire(cron or "", base)
    except CronError as exc:
        raise BusinessError(str(exc)) from exc


def _to_response(s: TaskSchedule) -> TaskScheduleResponse:
    return TaskScheduleResponse(
        id=s.id,  # type: ignore[arg-type]
        name=s.name,
        task_type=s.task_type,
        payload=dict(s.payload or {}),
        cron=s.cron,
        interval_seconds=s.interval_seconds,
        enabled=s.enabled,
        next_fire_at=s.next_fire_at,
        last_fired_at=s.last_fired_at,
        last_task_id=s.last_task_id,
        last_status=s.last_status,
        remark=s.remark,
        created_by=s.created_by,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _wake_local_scheduler() -> None:
    """热更后唤醒 local 调度循环(立即重算休眠; celery 引擎下无循环, 静默忽略)"""
    try:
        from module_task.tasks.scheduler import wake_scheduler

        wake_scheduler()
    except Exception:  # noqa: BLE001  # 循环未启动/未导入属正常态, 不影响落库热更
        pass


class TaskScheduleService:
    def __init__(self, dao: TaskScheduleDao, task_service: TaskQueueService):
        """依赖注入构造器: 调度DAO + 任务队列服务(触发时复用其创建/派发链路)"""
        self.dao = dao
        self.task_service = task_service

    # ################ 查询 ################

    async def list_page(
        self,
        pagination: PaginationParams,
        keyword: str | None = None,
        enabled: bool | None = None,
        task_type: str | None = None,
    ) -> PaginationResponse:
        """分页查询调度列表"""
        items = await self.dao.list_page(
            pagination, keyword=keyword, enabled=enabled, task_type=task_type
        )
        total = await self.dao.count(keyword=keyword, enabled=enabled, task_type=task_type)
        return PaginationResponse.create([_to_response(s) for s in items], total, pagination)

    # ################ CRUD(热更) ################

    async def create(self, data: TaskScheduleCreate, user_id: str) -> TaskScheduleResponse:
        """
        创建调度定义(校验通过即重算下次触发并唤醒循环)
        :raises BusinessError: 类型未注册/触发方式缺失或冲突/cron 非法
        """
        _validate_definition(data.task_type, data.cron, data.interval_seconds)
        now = datetime.now(timezone.utc)
        schedule = TaskSchedule(
            name=data.name,
            task_type=data.task_type,
            payload=data.payload or {},
            cron=data.cron or None,
            interval_seconds=data.interval_seconds,
            enabled=False,  # 先落定义再启用(下面统一走重算逻辑)
            remark=data.remark,
            created_by=user_id,
        )
        schedule.next_fire_at = compute_next_fire(data.cron, data.interval_seconds, now)
        schedule.enabled = bool(data.enabled)
        if not schedule.enabled:
            schedule.next_fire_at = None
        schedule.id = await self.dao.add(schedule)
        _wake_local_scheduler()
        return _to_response(schedule)

    async def update(self, schedule_id: int, data: TaskScheduleUpdate) -> TaskScheduleResponse:
        """
        修改调度(启停/改周期即时热生效: 重算 next_fire_at 并唤醒 local 循环)
        :raises NotFoundError: 调度不存在
        :raises BusinessError: 校验失败
        """
        schedule = await self.dao.get(schedule_id)
        if not schedule:
            raise NotFoundError(f"未找到ID为 {schedule_id} 的调度")
        _validate_definition(data.task_type, data.cron, data.interval_seconds)

        now = datetime.now(timezone.utc)
        schedule.name = data.name
        schedule.task_type = data.task_type
        schedule.payload = data.payload or {}
        schedule.cron = data.cron or None
        schedule.interval_seconds = data.interval_seconds
        schedule.remark = data.remark
        if data.enabled:
            # 启用: 错过窗口不补跑, 从当前时刻重算
            schedule.next_fire_at = compute_next_fire(schedule.cron, schedule.interval_seconds, now)
        else:
            schedule.next_fire_at = None
        schedule.enabled = bool(data.enabled)
        await self.dao.update(schedule)
        _wake_local_scheduler()
        return _to_response(schedule)

    async def delete(self, schedule_id: int) -> None:
        """删除调度定义(已派发任务不受影响)"""
        await self.dao.delete(schedule_id)
        _wake_local_scheduler()

    # ################ 触发 ################

    async def trigger_now(self, schedule_id: int) -> TaskScheduleTriggerResult:
        """
        手动立即触发一次(不改动周期调度节奏, 常用于验证任务定义)
        :return: 生成的任务ID
        """
        schedule = await self.dao.get(schedule_id)
        if not schedule:
            raise NotFoundError(f"未找到ID为 {schedule_id} 的调度")
        task = await self._fire(schedule, datetime.now(timezone.utc))
        return TaskScheduleTriggerResult(task_id=task.id, schedule_id=schedule_id)

    async def _fire(self, schedule: TaskSchedule, fired_at: datetime):
        """
        触发单个调度: 复用任务队列创建/双引擎派发链路生成 task_queue 记录
        (payload 注入 _schedule_id 便于追溯; 派发失败不抛出, 回写快照供前端排查)
        """
        task = await self.task_service.create(
            TaskQueueCreate(
                name=schedule.name,
                task_type=schedule.task_type,
                payload={**(schedule.payload or {}), "_schedule_id": schedule.id},
            ),
            user_id=schedule.created_by,
        )
        schedule.last_fired_at = fired_at
        schedule.last_task_id = task.id
        schedule.last_status = "ok"
        await self.dao.update(schedule)
        return task

    # ################ 调度器 tick(local 循环与 celery beat 共用) ################

    async def scan_due_and_dispatch(self) -> int:
        """
        扫描到期调度并派发(local 循环每轮/celery beat 每分钟调用一次)
        :return: 本轮派发的调度数

        语义要点:
            - 停机错过的不补跑(以当前时刻重算, 防历史窗口雪崩)
            - 触发推进以本次 next_fire_at 为基准(固定间隔不累积漂移)
            - 单个调度派发失败只记快照, 不中断本轮其余调度
        """
        now = datetime.now(timezone.utc)
        due = await self.dao.due_schedules(now, limit=TICK_BATCH)
        fired = 0
        for schedule in due:
            try:
                await self._fire(schedule, now)
                fired += 1
                logger.info(f"调度触发: {schedule.name} -> 任务 {schedule.last_task_id}")
            except Exception as exc:  # noqa: BLE001  # 单点失败不阻断整轮
                schedule.last_fired_at = now
                schedule.last_status = "dispatch_failed"
                logger.warning(f"调度 {schedule.name} 派发失败: {exc}")
                await self.dao.update(schedule)
            # 推进下次触发(以本次计划时刻为基准防漂移; 已落后则从现在重算跳过错过窗口)
            base = schedule.next_fire_at or now
            nxt = compute_next_fire(schedule.cron, schedule.interval_seconds, base)
            if nxt <= now:
                nxt = compute_next_fire(schedule.cron, schedule.interval_seconds, now)
            schedule.next_fire_at = nxt
            await self.dao.update(schedule)
        return fired
