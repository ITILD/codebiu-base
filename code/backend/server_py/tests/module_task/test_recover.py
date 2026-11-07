"""任务自愈测试: 遗留 PENDING 重派发 + 僵尸 RUNNING 清扫(memory broker, 零外网)"""
from datetime import datetime, timedelta, timezone

from module_task.dao.task import TaskQueueDao
from module_task.do.task import QueueTaskStatus, TaskQueue
from module_task.tasks import fail_stale_running_tasks, recover_pending_tasks


async def _add_task(**overrides) -> TaskQueue:
    """插入测试任务(默认 sys_audit_purge 类型)并返回带 id 的记录"""
    fields = dict(
        name="自愈测试任务",
        task_type="sys_audit_purge",
        payload={},
        user_id="u_test_recover",
        status=QueueTaskStatus.RUNNING,
    )
    fields.update(overrides)
    task = TaskQueue(**fields)
    task.id = await TaskQueueDao().add(task)
    return task


async def test_recover_redispatches_stale_pending():
    """创建超 60s 仍 PENDING 且无投递ID → 重派发并回写 celery_task_id"""
    task = await _add_task(
        status=QueueTaskStatus.PENDING,
        celery_task_id=None,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    try:
        recovered = await recover_pending_tasks()
        assert recovered >= 1
        refreshed = await TaskQueueDao().get(task.id)
        assert refreshed is not None
        assert refreshed.celery_task_id  # 已重新投递(memory broker 返回消息ID)
        assert refreshed.status == QueueTaskStatus.PENDING
    finally:
        await TaskQueueDao().delete(task.id)


async def test_sweep_fails_stale_running_without_heartbeat():
    """RUNNING 超 30 分钟无 Celery 心态(worker 崩溃遗留) → 置 FAILED 归档"""
    task = await _add_task(
        celery_task_id=None,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=40),
    )
    try:
        swept = await fail_stale_running_tasks(stale_minutes=30)
        assert swept >= 1
        refreshed = await TaskQueueDao().get(task.id)
        assert refreshed is not None
        assert refreshed.status == QueueTaskStatus.FAILED
        assert "无心跳" in (refreshed.error or "")
        assert refreshed.finished_at is not None
    finally:
        await TaskQueueDao().delete(task.id)


async def test_sweep_keeps_recent_running():
    """近期 RUNNING(未超时)不清扫, 长任务不受影响"""
    task = await _add_task(
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    try:
        swept = await fail_stale_running_tasks(stale_minutes=30)
        refreshed = await TaskQueueDao().get(task.id)
        assert refreshed is not None
        assert refreshed.status == QueueTaskStatus.RUNNING
        assert swept == 0
    finally:
        await TaskQueueDao().delete(task.id)


async def test_sweep_keeps_heartbeat_progress_task():
    """超时 RUNNING 但结果后端仍有 PROGRESS 心跳(实际仍在跑) → 跳过不误杀"""
    from common.config.tasks import app as celery_app

    task = await _add_task(
        celery_task_id="fake-celery-id-heartbeat",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=40),
    )
    # 模拟 worker 周期回写的进度心跳(结果后端可见)
    celery_app.backend.store_result(
        "fake-celery-id-heartbeat", {"progress": 50.0}, "PROGRESS"
    )
    try:
        swept = await fail_stale_running_tasks(stale_minutes=30)
        refreshed = await TaskQueueDao().get(task.id)
        assert refreshed is not None
        assert refreshed.status == QueueTaskStatus.RUNNING
        assert swept == 0
    finally:
        await TaskQueueDao().delete(task.id)
