"""任务队列 Celery 配置(模块级单例)

- broker/backend 从 config.yaml 的 tasks 段读取(也可在 系统管理→通用配置 动态修改)
- 任务统一经 Redis broker 派发, 由 app_task.py worker 进程消费执行
- 未配置 broker 时默认 memory:// 本地内存队列(无需额外服务,适合开发/测试;
  注意 memory broker 消息不出进程, 需启动 worker 才会真实执行)
- 生产部署配置 redis 即可,如:
    tasks:
      broker_url: redis://127.0.0.1:6379/1
      result_backend: redis://127.0.0.1:6379/2
"""
import logging

from common.config.index import conf

logger = logging.getLogger(__name__)

try:
    conf_tasks = conf.tasks
    if conf_tasks is None:
        conf_tasks = {}
except Exception:
    conf_tasks = {}

BROKER_URL: str = conf_tasks.get("broker_url", "memory://")
RESULT_BACKEND: str = conf_tasks.get("result_backend", "cache+memory://")

_celery_app = None  # Celery 实例缓存(首次访问 app 时才创建)


def _build_celery_app():
    """惰性创建 Celery 实例(celery 库与实例创建延迟到首次访问)"""
    from celery import Celery

    app = Celery(
        "base_server",
        broker=BROKER_URL,
        backend=RESULT_BACKEND,
        # 导入各模块注册的任务(按需追加)
        include=[
            "module_task.tasks.demo",
            "module_task.tasks.maintenance",
            "module_task.tasks.schedule_beat",
            "module_rag.tasks.project_document",
            "module_rag.tasks.project_document_chunk",
        ],
    )

    # 序列化与结果过期配置
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=3600,
        timezone="Asia/Shanghai",
        # 默认队列(与 app_task.py worker 消费的队列一致)
        task_default_queue="task_queue",
        broker_connection_retry_on_startup=True,
        # 任务优先级(Redis 分级队列): priority 0~9, 数值越大越先被消费;
        # 生产者(send_task)与消费者(worker)共用本配置, 分级子队列语义一致
        broker_transport_options={
            "priority_steps": list(range(10)),
            "queue_order_strategy": "priority",
        },
        task_inherit_parent_priority=True,
        # 周期调度 beat(REQ-012): 每分钟 tick 一次, 调度定义落库热更
        # (无需随调度增改重启 beat); 仅启动 beat 进程时生效
        beat_schedule={
            "task-scheduler-tick": {
                "task": "module_task.tasks.schedule_beat.tick_scheduled_tasks",
                "schedule": 60.0,
            }
        },
    )

    logger.debug(f"ok...tasks celery配置加载完成 broker={BROKER_URL}")
    return app


def __getattr__(name):
    """PEP 562 模块级惰性属性: `from common.config.tasks import app` 访问时才触发创建"""
    if name == "app":
        global _celery_app
        if _celery_app is None:
            _celery_app = _build_celery_app()
        return _celery_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def refresh_tasks_runtime() -> None:
    """从动态配置刷新 broker/backend 快照(init_runtime 装配时与配置更新钩子调用)"""
    try:
        from common.config.dynamic import get_settings
        from common.config.dynamic.schemas import TasksSettings

        s = await get_settings(TasksSettings)
        broker, backend = s.broker_url, s.result_backend
    except Exception:
        return  # runtime/动态配置未就绪(如纯 import 场景), 保留 yaml 兜底值
    global BROKER_URL, RESULT_BACKEND
    BROKER_URL, RESULT_BACKEND = broker, backend
    logger.info(f"任务队列配置快照已刷新: broker={broker}")


def invalidate_celery_app() -> None:
    """配置更新钩子: 使缓存的 celery app 失效, 下次访问 app 时按新参数重建"""
    global _celery_app
    _celery_app = None
