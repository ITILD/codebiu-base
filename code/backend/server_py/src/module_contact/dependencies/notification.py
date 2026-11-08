"""通知中心 FastAPI 依赖注入(REQ-011)"""

from fastapi import Depends

from module_contact.dao.notification import ContactMessageDao, ContactSubscriptionDao
from module_contact.service.notification import NotificationService
from module_contact.service.verify_code import get_verify_code_service


async def get_notification_service() -> NotificationService:
    """通知中心Service工厂(组合站内信/订阅DAO与验证码服务, 外部通道默认全局单例)"""
    return NotificationService(
        ContactMessageDao(),
        ContactSubscriptionDao(),
        verify_code_service=get_verify_code_service(),
    )
