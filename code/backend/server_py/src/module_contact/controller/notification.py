"""通知中心接口层(REQ-011): 站内信自助操作与订阅开关

鉴权策略: 通知属用户个人数据, 登录即可(get_current_user_id),
不设管理权限节点(不进权限树); 数据隔离由 service/dao 按当前用户过滤保证。
"""

from fastapi import APIRouter, Depends, Query, status

from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_authorization.dependencies.auth import get_current_user_id
from module_contact.config.server import module_app
from module_contact.dependencies.notification import get_notification_service
from module_contact.do.notification import (
    ContactMessageResponse,
    ContactSubscriptionResponse,
    ContactSubscriptionUpdate,
)
from module_contact.service.notification import NotificationService

router = APIRouter()


@router.get("/list", summary="分页查询我的通知", response_model=PaginationResponse)
async def list_notifications(
    pagination: PaginationParams = Depends(),
    is_read: bool | None = Query(None, description="已读过滤"),
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> PaginationResponse:
    """分页查询当前用户站内信(时间倒序)"""
    return await service.list_page(pagination, current_user_id, is_read=is_read)


@router.get("/unread-count", summary="未读通知数")
async def unread_count(
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> dict:
    """未读数(前端顶栏铃铛轮询)"""
    return {"count": await service.unread_count(current_user_id)}


@router.put("/{message_id}/read", summary="标记单条已读", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    message_id: int,
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """标记单条已读(仅本人通知可标记)"""
    await service.mark_read(current_user_id, message_id)


@router.put("/read-all", summary="全部已读", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """当前用户通知全部已读"""
    await service.mark_all_read(current_user_id)


@router.delete("", summary="清空我的通知", status_code=status.HTTP_204_NO_CONTENT)
async def clear_notifications(
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """清空当前用户全部站内信(含已读, 不可恢复)"""
    await service.clear(current_user_id)


@router.get("/subscriptions", summary="我的订阅矩阵", response_model=list[ContactSubscriptionResponse])
async def list_subscriptions(
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> list[ContactSubscriptionResponse]:
    """通知类型 x 外部通道 的当前订阅开关(未设置默认关闭)"""
    return await service.get_subscriptions(current_user_id)


@router.put("/subscriptions", summary="设置订阅开关", response_model=ContactSubscriptionResponse)
async def set_subscription(
    data: ContactSubscriptionUpdate,
    current_user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> ContactSubscriptionResponse:
    """
    设置单个订阅开关(通知类型 x 通道)
    :raises BusinessError: 通知类型或通道非法(400)
    """
    return await service.set_subscription(
        current_user_id, data.notify_type, data.channel, data.enabled
    )


module_app.include_router(router, prefix="/notifications", tags=["通知中心"])
