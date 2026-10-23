"""
celery 引擎周期调度 tick(REQ-012, 仅 tasks.engine=celery 时由 beat 触发)

设计(local/celery 双引擎同一扫描主体):
    beat 只配一个每分钟的 tick 任务, 调度定义全部落库(task_schedule 表)热生效 ——
    新增/启停/改周期无需改 beat 配置重启; tick 内部调用与 local 循环完全相同的
    service.scan_due_and_dispatch()(到期间隔查询 + 单轮限 20 条, 多 worker 部署时
    重复触发由 next_fire_at 推进的乐观语义自然幂等收敛)。

启动(与 worker 同一入口文件):
    celery -A src.app_task worker   # 任务执行进程(已有)
    celery -A src.app_task beat     # 调度触发进程(需要周期任务时额外启动, 单实例)

注意: 本文件仅在 worker/beat 进程导入(app_task.py 与 celery include 列表),
Web 进程(local 引擎)不导入, 保持零 celery 加载。
"""
import logging

from common.config.tasks import app as celery_app
from module_task.tasks import run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="module_task.tasks.schedule_beat.tick_scheduled_tasks")
def tick_scheduled_tasks() -> dict:
    """每分钟由 beat 触发: 扫描到期调度并按当前引擎派发(空转时仅一次索引查询)"""
    from module_task.service.schedule import TaskScheduleService

    async def _tick() -> dict:
        # 动态开关(tasks.scheduler_enabled): 关闭时空转返回, 无需摘除 beat 配置
        from common.config.dynamic import get_settings
        from common.config.dynamic.schemas import TasksSettings

        settings = await get_settings(TasksSettings)
        if not settings.scheduler_enabled:
            return {"enabled": False, "fired": 0}
        from module_task.dao.schedule import TaskScheduleDao
        from module_task.dao.task import TaskQueueDao
        from module_task.service.task import TaskQueueService

        service = TaskScheduleService(
            TaskScheduleDao(), TaskQueueService(TaskQueueDao())
        )
        return {"enabled": True, "fired": await service.scan_due_and_dispatch()}

    result = run_async(_tick())
    if result.get("fired"):
        logger.info("beat tick 派发 %s 个到期调度", result["fired"])
    return result


def build_beat_schedule() -> dict:
    """
    生成 celery beat 配置(固定单条 tick, 调度定义在库中热更, 见模块 docstring)
    供部署侧引用核对; 实际生效配置由 common.config.tasks._build_celery_app 装配
    """
    return {
        "task-scheduler-tick": {
            "task": "module_task.tasks.schedule_beat.tick_scheduled_tasks",
            "schedule": 60.0,  # 分钟级精度与 local 引擎对齐
        }
    }
