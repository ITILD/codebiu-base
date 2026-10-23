"""通知中心 FastAPI 依赖注入(REQ-011)"""

from fastapi import Depends

from module_contact.dao.notification import ContactMessageDao, ContactSubscriptionDao
from module_contact.service.notification import NotificationService


async def get_notification_service() -> NotificationService:
    """通知中心Service工厂(组合站内信/订阅DAO, 外部通道默认全局单例)"""
    return NotificationService(ContactMessageDao(), ContactSubscriptionDao())
