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


# 内置示例调度(REQ-012): 审计日志周期清理, 默认停用由管理员按需启用
_DEMO_SCHEDULE_NAME = "审计日志周期清理"
_DEMO_SCHEDULE_CRON = "0 4 * * *"  # 每日 04:00


@register_init_hook
async def seed_demo_schedule() -> None:
    """
    周期调度启动装配(REQ-012): 播种内置示例(sys_audit_purge 审计清理,
    幂等: 按名称查重, 默认停用)。周期触发由独立 beat 进程负责
    (celery -A src.app_task beat, 每分钟 tick, 调度定义落库热更), API 进程不跑循环。
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


logger.debug("ok...server module_task服务配置")
