"""通知中心进程内发布订阅中心(SSE 实时未读推送)

结构: ``{user_id: set[asyncio.Queue]}``, 全部增删/发布操作经 ``asyncio.Lock`` 保护。

约束:
    - 单进程语义: 多 worker 部署时仅推送本进程产生的通知(跨进程需外部消息总线)
    - 队列满时丢弃最旧一条后写入, publish 永不阻塞(慢客户端不拖累通知落库链路)
    - 无订阅者时静默返回
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 单连接事件缓冲上限(慢客户端最多积压 100 条事件)
DEFAULT_QUEUE_SIZE = 100


class NotificationSubscription:
    """单个 SSE 连接的订阅句柄(queue + 异步退订, 支持 async with)"""

    def __init__(
        self, hub: "NotificationHub", user_id: str, queue: asyncio.Queue
    ):
        self._hub = hub
        self._user_id = user_id
        self.queue = queue
        self._active = True

    async def unsubscribe(self) -> None:
        """退订(幂等): 从中心移除队列, 供 finally 调用防泄漏"""
        if not self._active:
            return
        self._active = False
        await self._hub.unsubscribe(self._user_id, self.queue)

    async def __aenter__(self) -> "NotificationSubscription":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.unsubscribe()


class NotificationHub:
    """进程内通知事件中心(按用户维度的多队列广播)"""

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE):
        """
        :param queue_size: 单连接队列容量(满时丢弃最旧事件)
        """
        self._queues: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._queue_size = queue_size

    async def subscribe(self, user_id: str) -> NotificationSubscription:
        """为用户建立订阅(每个 SSE 连接一个独立队列)"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._queues.setdefault(user_id, set()).add(queue)
        return NotificationSubscription(self, user_id, queue)

    async def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        """移除订阅队列(用户无剩余连接时清理空集合)"""
        async with self._lock:
            queues = self._queues.get(user_id)
            if queues is None:
                return
            queues.discard(queue)
            if not queues:
                self._queues.pop(user_id, None)

    async def publish(self, user_id: str, event: str, data: Any) -> None:
        """
        向用户全部连接广播事件(无订阅者静默返回)

        :param user_id: 目标用户ID
        :param event: SSE 事件名(notification/unread 等)
        :param data: 事件数据(由接口层序列化为 JSON)
        """
        async with self._lock:
            queues = list(self._queues.get(user_id) or ())
        if not queues:
            return
        for queue in queues:
            if queue.full():
                # 丢弃最旧一条, 避免慢客户端阻塞发布方
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # 并发消费导致的极端情况
                    pass
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:  # 理论上不会触发(已腾位), 兜底防抛
                logger.warning(f"通知事件队列已满, 丢弃事件(user_id={user_id})")


# 全局单例(进程内共享; notification service 与 SSE 接口共用)
notification_hub = NotificationHub()


def get_notification_hub() -> NotificationHub:
    """NotificationHub 依赖注入工厂"""
    return notification_hub
