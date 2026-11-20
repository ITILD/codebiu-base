"""
worker 侧动态队列订阅(worker_ready 对齐 + 周期对账)

设计说明(队列数弹性 ≠ 进程数弹性的解耦落地):
    1. 队列注册表(sys_task_queue_registry)是订阅关系的唯一事实来源;
       加/撤队列在主服务侧落库即生效, worker 通过广播 add_consumer/cancel_consumer
       秒级增减订阅, 无需重启容器 —— 副本伸缩(容器数)才需要 agent 运维。
    2. Celery 的动态订阅不持久化(重启即失), 因此:
       - worker_ready 信号触发首次对齐(从注册表补齐全部启用队列);
       - 之后每 60s 周期对账一次(diff 注册表 vs 实际 active_queues),
       兼容外部广播(主服务"定向订阅"接口)造成的偏差。
    3. 订阅模式二选一(由启动环境决定):
       - 动态模式(未设 TASK_QUEUES/WORKER_QUEUES): 跟随注册表全量对账(默认);
       - 固定模式(显式指定了队列): 运维刻意物理隔离(如交互专用 worker),
         完全跳过对账, 注册表变化不影响其订阅。
    4. 仅 worker 角色加载本模块(由 app_task.py 导入); API 进程不触发 celery 信号。
"""
import logging
import os
import threading
import time

from celery.signals import worker_ready

logger = logging.getLogger(__name__)

# 周期对账参数
_RECONCILE_INTERVAL = 60  # 对账周期(秒)
_RECONCILE_WARMUP = 3     # worker_ready 后先等 pidbox 控制通道稳定
_INSPECT_TIMEOUT = 2      # 自查询 active_queues 的应答超时(秒)

_node_name: str | None = None   # 本 worker 节点名(worker_ready 时确定)


def _explicit_pinned() -> bool:
    """是否显式固定了消费队列(固定模式跳过注册表对账)"""
    return bool(os.environ.get("TASK_QUEUES") or os.environ.get("WORKER_QUEUES"))


def _current_queues(node: str) -> set[str] | None:
    """
    查询本 worker 当前实际订阅的队列集合(经 broker 自查询, 事实来源)
    :return: 队列名集合; 查询失败返回 None(调用方跳过本轮对账, 不做误判)
    """
    from common.config.tasks import app as celery_app

    try:
        insp = celery_app.control.inspect(timeout=_INSPECT_TIMEOUT)
        result = insp.active_queues(destination=[node]) or {}
        queues = result.get(node) or []
        return {q["name"] for q in queues if q.get("name")}
    except Exception as exc:
        logger.debug(f"查询本节点 active_queues 失败(跳过本轮对账): {exc}")
        return None


def _reconcile_once(node: str) -> None:
    """
    单轮对账: 注册表启用队列 vs 实际订阅 → 增 add_consumer / 减 cancel_consumer
    (广播目标限定本节点, 不影响其他 worker 的订阅)
    """
    from common.config.tasks import app as celery_app
    from module_task.tasks import enabled_registry_queues, run_async

    desired = run_async(enabled_registry_queues())
    if desired is None:
        return  # 注册表不可读(DB 异常): 保持现状, 下轮再试
    current = _current_queues(node)
    if current is None:
        return  # 自查询失败: 保持现状, 下轮再试

    to_add = desired - current
    to_cancel = current - desired
    if not to_add and not to_cancel:
        return
    for queue in sorted(to_add):
        try:
            celery_app.control.add_consumer(queue, destination=[node])
            logger.info(f"动态订阅: 已增加消费队列 {queue}")
        except Exception as exc:
            logger.warning(f"动态订阅失败(add_consumer {queue}): {exc}")
    for queue in sorted(to_cancel):
        try:
            celery_app.control.cancel_consumer(queue, destination=[node])
            logger.info(f"动态订阅: 已取消消费队列 {queue}")
        except Exception as exc:
            logger.warning(f"动态退订失败(cancel_consumer {queue}): {exc}")


def _reconcile_loop(node: str) -> None:
    """周期对账线程(worker_ready 后启动, 守护线程)"""
    time.sleep(_RECONCILE_WARMUP)
    logger.info(
        f"队列订阅对账线程已启动(周期 {_RECONCILE_INTERVAL}s, 节点 {node}, 模式=动态)"
    )
    while True:
        try:
            _reconcile_once(node)
        except Exception as exc:  # 单轮失败不影响下轮
            logger.debug(f"队列对账异常(忽略): {exc}")
        time.sleep(_RECONCILE_INTERVAL)


@worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):
    """
    worker 就绪钩子: 确定节点名并启动对账线程

    固定模式(显式指定队列)直接跳过 —— 订阅关系由启动参数决定, 不对账。
    """
    global _node_name
    if _explicit_pinned():
        logger.info("已显式指定消费队列(固定模式), 跳过注册表动态对账")
        return
    hostname = getattr(sender, "hostname", None)
    if not hostname:
        import socket

        hostname = (
            os.environ.get("TASK_WORKER_NAME", "").strip()
            or f"task_worker@{socket.gethostname()}#{os.getpid()}"
        )
    _node_name = hostname
    threading.Thread(
        target=_reconcile_loop, args=(hostname,), daemon=True, name="task-queue-sync"
    ).start()
