"""队列注册表接口层: 逻辑队列的登记/启停/删除与动态订阅广播"""

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, status

from module_authorization.dependencies.permission import require_permission
from module_task.config.server import module_app
from module_task.dependencies.task import get_queue_registry_service
from module_task.do.task import (
    TaskQueueRegistryCreate,
    TaskQueueRegistryUpdate,
    TaskQueueRegistryView,
)
from module_task.service.queue_registry import TaskQueueRegistryService

router = APIRouter()


@router.get("", summary="查询队列注册表", response_model=list[TaskQueueRegistryView])
async def list_queues(
    current_user_id: str = Depends(require_permission("task", "queue", "read")),
    service: TaskQueueRegistryService = Depends(get_queue_registry_service),
) -> list[TaskQueueRegistryView]:
    """队列注册表列表(含实时订阅 worker 数与积压深度)"""
    return await service.list_views()


@router.post("", summary="登记新队列", status_code=status.HTTP_201_CREATED,
             response_model=TaskQueueRegistryView)
async def create_queue(
    data: TaskQueueRegistryCreate,
    current_user_id: str = Depends(require_permission("task", "queue", "create")),
    service: TaskQueueRegistryService = Depends(get_queue_registry_service),
) -> TaskQueueRegistryView:
    """
    登记新队列(落库即生效): worker 动态订阅模式 60s 内自动对齐,
    也可调 subscribe 接口立即拉起订阅 —— 不需要重启/新增任何容器
    """
    return await service.create(data)


@router.patch("/{queue_name}", summary="更新队列属性/启停",
              response_model=TaskQueueRegistryView)
async def update_queue(
    queue_name: str,
    data: TaskQueueRegistryUpdate,
    current_user_id: str = Depends(require_permission("task", "queue", "update")),
    service: TaskQueueRegistryService = Depends(get_queue_registry_service),
) -> TaskQueueRegistryView:
    """更新队列属性; 启用/停用即时广播订阅增减(秒级生效)"""
    return await service.update(queue_name, data)


@router.delete("/{queue_name}", summary="删除队列登记", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue(
    queue_name: str,
    current_user_id: str = Depends(require_permission("task", "queue", "delete")),
    service: TaskQueueRegistryService = Depends(get_queue_registry_service),
) -> None:
    """删除队列登记(内置队列不允许删除; 仍有 worker 订阅时请先停用等待退订)"""
    await service.delete(queue_name)


class QueueSubscribeBody(BaseModel):
    """定向订阅请求体(不传 worker = 广播全部动态模式 worker)"""

    worker: str | None = Field(default=None, description="目标 worker 节点名(空=广播全部)")


@router.post("/{queue_name}/subscribe", summary="广播增加队列订阅",
             response_model=int)
async def subscribe_queue(
    queue_name: str,
    body: QueueSubscribeBody | None = None,
    current_user_id: str = Depends(require_permission("task", "queue", "update")),
    service: TaskQueueRegistryService = Depends(get_queue_registry_service),
) -> int:
    """
    广播 add_consumer(秒级生效, 不等 worker 周期对账)
    :return: 确认订阅的 worker 数
    """
    worker = body.worker if body else None
    return await service.broadcast_subscribe(queue_name, worker)


@router.post("/{queue_name}/unsubscribe", summary="广播取消队列订阅",
             response_model=int)
async def unsubscribe_queue(
    queue_name: str,
    body: QueueSubscribeBody | None = None,
    current_user_id: str = Depends(require_permission("task", "queue", "update")),
    service: TaskQueueRegistryService = Depends(get_queue_registry_service),
) -> int:
    """广播 cancel_consumer(固定订阅的 worker 不受影响)"""
    worker = body.worker if body else None
    return await service.broadcast_cancel(queue_name, worker)


module_app.include_router(router, prefix="/queues", tags=["队列注册表"])
