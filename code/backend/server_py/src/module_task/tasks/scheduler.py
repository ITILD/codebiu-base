"""
local 引擎周期调度循环(REQ-012, 纯 asyncio 无 Celery 依赖)

运行模型(内存占用最小化):
    单个后台协程, 无常驻调度缓存 —— 每轮只做一次索引查询:
      1. 查最早 next_fire_at → 计算休眠秒数(截断在 [1s, 30s])
      2. asyncio.Event 带超时等待(调度定义热更时被唤醒提前返回)
      3. 到点扫描到期调度并派发(service.scan_due_and_dispatch, 单轮限 20 条)
    30 秒休眠上限保证: 直接改库等旁路变更最迟 30s 内被感知;
    进程终止时协程随事件循环销毁, 无状态无锁, 中断轮次由
    "错过不补跑"语义自愈(下次启动从当前时刻重算)。

接线: module_task.config.server 启动钩子在 tasks.engine=local 且
      tasks.scheduler_enabled 时调用 start_scheduler();
      celery 引擎改由 beat 每分钟触发 tasks/schedule_beat.py 的 tick 任务,
      扫描主体与本模块共用同一 service.scan_due_and_dispatch。
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# 休眠截断区间: 下限防惊群空转, 上限保证旁路变更(直接改库)最迟 30s 被感知
_MIN_SLEEP, _MAX_SLEEP = 1.0, 30.0
# 扫描异常后的退避间隔(数据库抖动时避免每秒重试刷屏)
_ERROR_BACKOFF = 5.0

_wake_event: asyncio.Event | None = None  # 惰性创建(绑定当前事件循环)
_loop_task: asyncio.Task | None = None


def wake_scheduler() -> None:
    """唤醒调度循环(调度定义热更后立即重算休眠; 循环未启动时静默忽略)"""
    if _wake_event is not None and not _wake_event.is_set():
        _wake_event.set()


async def _scheduler_loop() -> None:
    """调度主循环: 睡到最近触发时刻(或被唤醒) → 扫描派发 → 循环"""
    from datetime import datetime, timezone

    from module_task.dao.schedule import TaskScheduleDao
    from module_task.dao.task import TaskQueueDao
    from module_task.service.schedule import TaskScheduleService
    from module_task.service.task import TaskQueueService

    scan = TaskScheduleService(TaskScheduleDao(), TaskQueueService(TaskQueueDao()))
    logger.info("local 周期调度循环已启动(分钟级精度, 休眠截断 %.0fs)", _MAX_SLEEP)
    try:
        while True:
            try:
                earliest = await TaskScheduleDao().earliest_next_fire()
                if earliest is None:
                    sleep_for = _MAX_SLEEP  # 无启用中调度: 空转上限等待(被唤醒即重查)
                else:
                    delta = (earliest - datetime.now(timezone.utc)).total_seconds()
                    sleep_for = min(max(delta, _MIN_SLEEP), _MAX_SLEEP)
                assert _wake_event is not None
                try:
                    await asyncio.wait_for(_wake_event.wait(), timeout=sleep_for)
                except asyncio.TimeoutError:
                    pass
                _wake_event.clear()
                await scan.scan_due_and_dispatch()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  # 单轮异常退避后继续(调度器须常驻)
                logger.exception("调度循环本轮执行异常, %.0fs 后重试", _ERROR_BACKOFF)
                await asyncio.sleep(_ERROR_BACKOFF)
    except asyncio.CancelledError:
        logger.info("local 周期调度循环已停止")


def start_scheduler() -> None:
    """启动调度循环(须在事件循环内调用; 幂等, 已启动则忽略)"""
    global _wake_event, _loop_task
    if _loop_task is not None and not _loop_task.done():
        return
    _wake_event = asyncio.Event()
    _loop_task = asyncio.create_task(_scheduler_loop(), name="task-scheduler")


async def stop_scheduler() -> None:
    """停止调度循环(服务关停时调用; 未启动时静默)"""
    global _loop_task
    if _loop_task is None:
        return
    task, _loop_task = _loop_task, None
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
