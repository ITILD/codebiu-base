"""任务队列模块 子应用装配: 路由挂载与模块级初始化"""

from common.config.lifespan import register_init_hook
from common.utils.fastapi_ex.exceptions import BizFastAPI
import logging

from common.config.server import app

logger = logging.getLogger(__name__)

# 模块子应用(挂载到主应用 /task 路径下)
module_app = BizFastAPI()
app.mount("/task", module_app)

# 导入权限声明(注册到权限中心, 幂等)
from module_task.config.permissions import TASK_DEFINE  # noqa: F401, E402


@register_init_hook
async def recover_local_pending_tasks() -> None:
    """
    local 引擎 API 启动自愈: 无独立 worker 进程, 遗留的长期 PENDING 任务
    (如进程重启瞬间丢失的后台协程)由 API 启动时重新派发(进程内后台执行)。
    celery 引擎不在此恢复(由 app_task.py worker 启动时兜底)。
    """
    from common.config.tasks import TASK_ENGINE
    from module_task.tasks import recover_pending_tasks

    if TASK_ENGINE == "local":
        count = await recover_pending_tasks()
        if count:
            logger.info(f"local 引擎启动自愈: 恢复 {count} 个遗留 PENDING 任务")


# 内置示例调度(REQ-012): 审计日志周期清理, 默认停用由管理员按需启用
_DEMO_SCHEDULE_NAME = "审计日志周期清理"
_DEMO_SCHEDULE_CRON = "0 4 * * *"  # 每日 04:00


@register_init_hook
async def seed_and_start_scheduler() -> None:
    """
    周期调度启动装配(REQ-012):
    1. 播种内置示例(sys_audit_purge 审计清理, 幂等: 按名称查重, 默认停用)
    2. local 引擎且动态配置 tasks.scheduler_enabled 时启动进程内调度循环
       (celery 引擎由独立 beat 进程触发, API 进程不跑循环)
    """
    from module_task.dao.schedule import TaskScheduleDao
    from module_task.do.schedule import TaskSchedule

    dao = TaskScheduleDao()
    if await dao.get_by_name(_DEMO_SCHEDULE_NAME) is None:
        schedule = TaskSchedule(
            name=_DEMO_SCHEDULE_NAME,
            task_type="sys_audit_purge",
            cron=_DEMO_SCHEDULE_CRON,
            enabled=False,  # 默认停用: 避免新部署意外清理, 管理员在定时任务页启用
            next_fire_at=None,
            remark="内置示例: 按保留期(audit.retention_days)每日凌晨清理过期审计日志",
            created_by="system",
        )
        await dao.add(schedule)
        logger.info("已播种内置示例调度: 审计日志周期清理(默认停用)")

    from common.config.tasks import TASK_ENGINE

    if TASK_ENGINE != "local":
        return
    import sys

    if "pytest" in sys.modules:
        # 测试进程不启动常驻调度循环: 循环协程会改变 local runner 回写与
        # 取消的竞态时序(用例直接调 scan_due_and_dispatch 验证扫描语义即可)
        return
    try:
        from common.config.dynamic import get_settings
        from common.config.dynamic.schemas import TasksSettings

        if not (await get_settings(TasksSettings)).scheduler_enabled:
            logger.info("周期调度开关关闭(tasks.scheduler_enabled=false), 不启动调度循环")
            return
    except Exception:  # noqa: BLE001  # 动态配置未就绪时按默认开启处理
        pass
    from module_task.tasks.scheduler import start_scheduler

    start_scheduler()


logger.debug("ok...server module_task服务配置")
