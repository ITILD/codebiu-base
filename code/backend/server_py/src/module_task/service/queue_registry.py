"""
队列注册表服务层(逻辑队列动态增减, 队列数弹性与进程数弹性解耦)

职责:
    - 注册表 CRUD: 加/撤/启停队列(落库即生效, worker 60s 内自动对账订阅)
    - 定向订阅: 广播 add_consumer/cancel_consumer(秒级生效, 不等对账周期)
    - 聚合视图: 每队列的实时订阅 worker 数(inspect)与积压深度(broker LLEN)
    - 派发联动: 注册表为准入闸门(module_task.tasks.resolve_dispatch_queue)

安全约束:
    - 内置队列(task_queue/q_interactive)不可删除(派发路由依赖), 可停用
    - 删除前校验: 仍有 worker 订阅时拒绝(先停用等待退订, 再删除)
"""
import asyncio
import re

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_task.dao.task import TaskQueueDao
from module_task.do.task import (
    QueueRegistryStatus,
    TaskQueueRegistry,
    TaskQueueRegistryCreate,
    TaskQueueRegistryUpdate,
    TaskQueueRegistryView,
)
from module_task.service.task import queue_backlogs

# 内置队列(派发路由依赖, 禁止删除; 停用后派发自动回落)
_BUILTIN_QUEUES = {"task_queue", "q_interactive"}
# 队列名字符集(broker 队列名安全字符)
_QUEUE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$")


class TaskQueueRegistryService:
    def __init__(self, dao: TaskQueueDao):
        self.dao = dao

    # ################ 查询 ################

    async def list_views(self) -> list[TaskQueueRegistryView]:
        """注册表列表(含订阅 worker 数与积压深度, 供队列管理页)"""
        rows = await self.dao.list_queue_registry()
        subscribers = await asyncio.to_thread(self._subscriber_map)
        backlogs = queue_backlogs([r.queue_name for r in rows])
        return [
            TaskQueueRegistryView(
                queue_name=r.queue_name,
                name=r.name or r.queue_name,
                description=r.description,
                tenant=r.tenant,
                resource_class=r.resource_class,
                min_replicas=r.min_replicas,
                max_replicas=r.max_replicas,
                status=r.status,
                created_at=r.created_at,
                updated_at=r.updated_at,
                subscribers=subscribers.get(r.queue_name, 0),
                backlog=backlogs.get(r.queue_name, 0),
            )
            for r in rows
        ]

    @staticmethod
    def _subscriber_map() -> dict[str, int]:
        """inspect 各 worker 实际订阅 → {队列名: 订阅 worker 数}(broker 不可用时为空)"""
        try:
            from common.config.tasks import app as celery_app

            insp = celery_app.control.inspect(timeout=1.5)
            active = insp.active_queues() or {}
        except Exception:
            return {}
        counter: dict[str, int] = {}
        for queues in active.values():
            for q in queues or []:
                name = q.get("name")
                if name:
                    counter[name] = counter.get(name, 0) + 1
        return counter

    # ################ 创建/更新/删除 ################

    async def create(self, data: TaskQueueRegistryCreate) -> TaskQueueRegistryView:
        """
        登记新队列: 落库即生效(worker 动态模式 60s 内自动订阅, 也可调 subscribe 立即拉起)
        :raises BusinessError: 队列名非法 / 已存在
        """
        if not _QUEUE_NAME_RE.match(data.queue_name):
            raise BusinessError("队列名仅允许字母/数字/下划线/点/横线, 长度 1~100")
        if await self.dao.get_queue_registry(data.queue_name) is not None:
            raise BusinessError(f"队列 {data.queue_name} 已在注册表登记")
        row = TaskQueueRegistry(
            queue_name=data.queue_name,
            name=data.name or data.queue_name,
            description=data.description,
            tenant=data.tenant,
            resource_class=data.resource_class or "default",
            status=QueueRegistryStatus.ENABLED,
        )
        await self.dao.add_queue_registry(row)
        # 立即广播订阅(不等 worker 周期对账, 秒级生效)
        await self.broadcast_subscribe(data.queue_name)
        return (await self._view(row.queue_name))

    async def update(
        self, queue_name: str, data: TaskQueueRegistryUpdate
    ) -> TaskQueueRegistryView:
        """
        更新队列属性/启停: 启停即时广播订阅增减(秒级), 其余属性落库即可
        :raises NotFoundError: 队列未登记
        :raises BusinessError: 停用内置队列需二次确认语义由调用方保证(此处允许)
        """
        row = await self._get_or_404(queue_name)
        changed_status = False
        if data.name is not None:
            row.name = data.name
        if data.description is not None:
            row.description = data.description
        if data.tenant is not None:
            row.tenant = data.tenant
        if data.resource_class is not None:
            row.resource_class = data.resource_class
        if data.min_replicas is not None:
            row.min_replicas = data.min_replicas
        if data.max_replicas is not None:
            row.max_replicas = data.max_replicas
        if data.status is not None and data.status != row.status:
            row.status = data.status
            changed_status = True
        await self.dao.update_queue_registry(row)
        if changed_status:
            # 启用 → 广播订阅; 停用 → 广播退订(固定订阅的 worker 不受影响)
            if row.status == QueueRegistryStatus.ENABLED:
                await self.broadcast_subscribe(queue_name)
            else:
                await self.broadcast_cancel(queue_name)
        return await self._view(row.queue_name)

    async def delete(self, queue_name: str) -> None:
        """
        删除队列登记: 需无 worker 订阅(否则先停用等退订), 内置队列禁止删除
        :raises NotFoundError: 队列未登记
        :raises BusinessError: 内置队列 / 仍有 worker 订阅 / broker 无法核实
        """
        if queue_name in _BUILTIN_QUEUES:
            raise BusinessError(f"内置队列 {queue_name} 不允许删除(可停用)")
        await self._get_or_404(queue_name)
        subscribers = self._subscriber_map().get(queue_name, 0)
        if subscribers > 0:
            raise BusinessError(
                f"仍有 {subscribers} 个 worker 订阅 {queue_name}, 请先停用等待退订(约 60s)后再删除"
            )
        await self.dao.delete_queue_registry(queue_name)

    # ################ 动态订阅广播 ################

    @staticmethod
    async def broadcast_subscribe(queue_name: str, worker: str | None = None) -> int:
        """
        广播 add_consumer: 全部动态模式 worker(或 destination=指定 worker)增加订阅
        :param worker: 目标节点名(None=广播全部)
        :return: 确认订阅的 worker 数(无应答返回 0, 不视为错误)
        """
        def _broadcast() -> dict:
            from common.config.tasks import app as celery_app

            return celery_app.control.add_consumer(
                queue_name,
                destination=[worker] if worker else None,
                timeout=2.0,
                reply=True,
            ) or {}

        try:
            replies = await asyncio.to_thread(_broadcast)
            return len(replies)
        except Exception:
            return 0  # broker 不可用: 交给 worker 周期对账兜底

    @staticmethod
    async def broadcast_cancel(queue_name: str, worker: str | None = None) -> int:
        """广播 cancel_consumer(语义同 broadcast_subscribe, 方向相反)"""

        def _broadcast() -> dict:
            from common.config.tasks import app as celery_app

            return celery_app.control.cancel_consumer(
                queue_name,
                destination=[worker] if worker else None,
                timeout=2.0,
                reply=True,
            ) or {}

        try:
            replies = await asyncio.to_thread(_broadcast)
            return len(replies)
        except Exception:
            return 0

    # ################ 内部 ################

    async def _get_or_404(self, queue_name: str) -> TaskQueueRegistry:
        row = await self.dao.get_queue_registry(queue_name)
        if row is None:
            raise NotFoundError(f"队列 {queue_name} 未在注册表登记")
        return row

    async def _view(self, queue_name: str) -> TaskQueueRegistryView:
        views = {v.queue_name: v for v in await self.list_views()}
        return views[queue_name]
