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


# 队列注册表内置种子(P2): 仅首启空表时播种, 此后注册表由运维全权管理
_SEED_QUEUES = (
    ("task_queue", "批处理队列", "常规批处理任务(夜间批量/重解析/重向量化等)"),
    ("q_interactive", "交互队列", "会话交互任务(对话附件解析等用户在等的任务, priority>=7 自动路由)"),
)


@register_init_hook
async def seed_queue_registry() -> None:
    """
    队列注册表播种(P2): 空表时登记两个内置物理队列, 使 worker 动态订阅对账
    从首启即有事实来源; 非空(运维已增删)则完全不干预
    """
    from module_task.dao.task import TaskQueueDao
    from module_task.do.task import QueueRegistryStatus, TaskQueueRegistry

    dao = TaskQueueDao()
    if await dao.list_queue_registry():
        return  # 已有登记(含运维自定义), 不覆盖
    for queue_name, name, description in _SEED_QUEUES:
        await dao.add_queue_registry(
            TaskQueueRegistry(
                queue_name=queue_name,
                name=name,
                description=description,
                resource_class="default",
                status=QueueRegistryStatus.ENABLED,
            )
        )
    logger.info(f"队列注册表已播种 {len(_SEED_QUEUES)} 个内置队列: {[q[0] for q in _SEED_QUEUES]}")


logger.debug("ok...server module_task服务配置")
