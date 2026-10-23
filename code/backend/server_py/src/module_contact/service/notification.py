"""通知中心服务层(REQ-011)

职责:
    - notify 统一入口: 站内信必达落库 + 外部通道(邮件/短信)按用户订阅路由
    - 联系方式缺失自动降级站内(不报错, 只记录尝试送达的通道快照)
    - 站内信自助操作: 列表/未读数/已读/全部已读/清空(仅本人数据)
    - 订阅开关矩阵: NOTIFY_TYPES x 外部通道 展开(未落记录默认关闭)

内存与体积约束(REQ-011 交付要求):
    - 复用既有 EmailService/SmsService(aiosmtplib/httpx), 零新增依赖
    - 外部通道发送仅订阅命中时执行; 失败仅日志, 不重试不排队(防堆积)
"""

import logging

from common.config.db import db_manager
from common.utils.fastapi_ex.exceptions import BusinessError
from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_contact.dao.notification import ContactMessageDao, ContactSubscriptionDao
from module_contact.do.notification import (
    CHANNEL_EMAIL,
    CHANNEL_INAPP,
    CHANNEL_SMS,
    EXTERNAL_CHANNELS,
    NOTIFY_TYPES,
    ContactMessage,
    ContactMessageResponse,
    ContactSubscriptionResponse,
)
from module_contact.service.email import EmailService, get_email_service
from module_contact.service.sms import SmsService, get_sms_service

logger = logging.getLogger(__name__)


class NotificationService:
    """通知中心服务(站内必达 + 订阅路由外部通道)"""

    def __init__(
        self,
        message_dao: ContactMessageDao,
        subscription_dao: ContactSubscriptionDao,
        email_service: EmailService | None = None,
        sms_service: SmsService | None = None,
    ):
        """
        :param message_dao: 站内信DAO
        :param subscription_dao: 订阅DAO
        :param email_service: 邮件通道(默认全局单例; 测试可注入打桩)
        :param sms_service: 短信通道(默认全局单例; 测试可注入打桩)
        """
        self.message_dao = message_dao
        self.subscription_dao = subscription_dao
        self.email_service = email_service or get_email_service()
        self.sms_service = sms_service or get_sms_service()

    # ################ 发送 ################

    async def _load_user_contact(self, user_id: str) -> tuple[str | None, str | None]:
        """读用户联系方式(email/phone, 均可空; 跨模块只读 do 不引 service 防循环)"""
        from module_authorization.do.user import User

        async with db_manager.db_rel.session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                return None, None
            return user.email, user.phone

    async def notify(
        self, user_id: str, notify_type: str, title: str, content: str | None = None
    ) -> ContactMessage:
        """
        发送通知(站内信必达; 外部通道按订阅 + 联系方式路由)
        :param user_id: 收件人用户ID
        :param notify_type: 通知类型编码(NOTIFY_TYPES)
        :param title: 通知标题
        :param content: 通知正文(可空)
        :return: 已落库的站内信记录(channels 为尝试送达通道快照)

        外部通道发送失败仅记日志(channels 不回改): 站内信已保证必达,
        外部属尽力而为, 失败重试会拖慢调用方(多为任务终态回写链路)。
        """
        channels = [CHANNEL_INAPP]
        subscriptions = {
            row.channel: row.enabled
            for row in await self.subscription_dao.list_for_user(
                user_id=user_id, notify_type=notify_type
            )
        }
        email, phone = await self._load_user_contact(user_id)

        send_email = bool(subscriptions.get(CHANNEL_EMAIL)) and bool(email)
        send_sms = bool(subscriptions.get(CHANNEL_SMS)) and bool(phone)
        if send_email:
            channels.append(CHANNEL_EMAIL)
        if send_sms:
            channels.append(CHANNEL_SMS)

        message = ContactMessage(
            user_id=user_id,
            notify_type=notify_type,
            title=title,
            content=content,
            channels=channels,
        )
        message.id = await self.message_dao.add(message)

        if send_email and email:
            if not await self.email_service.send_notification(email, title, content or title):
                logger.warning(f"邮件通知发送失败(to={email}, title={title})")
        if send_sms and phone:
            if not await self.sms_service.send_notification(phone, title):
                logger.warning(f"短信通知发送失败(to={phone}, title={title})")
        return message

    # ################ 站内信自助操作 ################

    async def list_page(
        self, pagination: PaginationParams, user_id: str, is_read: bool | None = None
    ) -> PaginationResponse:
        """分页查询当前用户站内信"""
        items = await self.message_dao.list_page(pagination, user_id, is_read=is_read)
        total = await self.message_dao.count(user_id, is_read=is_read)
        return PaginationResponse.create(
            [
                ContactMessageResponse(
                    id=m.id,  # type: ignore[arg-type]
                    notify_type=m.notify_type,
                    title=m.title,
                    content=m.content,
                    channels=list(m.channels or []),
                    is_read=m.is_read,
                    created_at=m.created_at,  # type: ignore[arg-type]
                )
                for m in items
            ],
            total,
            pagination,
        )

    async def unread_count(self, user_id: str) -> int:
        """未读数(前端铃铛轮询, 走 user_id+is_read 复合索引)"""
        return await self.message_dao.count(user_id, is_read=False)

    async def mark_read(self, user_id: str, message_id: int) -> None:
        """标记单条已读"""
        await self.message_dao.mark_read(message_id, user_id)

    async def mark_all_read(self, user_id: str) -> int:
        """全部已读 :return: 标记条数"""
        return await self.message_dao.mark_all_read(user_id)

    async def clear(self, user_id: str) -> None:
        """清空当前用户全部站内信"""
        await self.message_dao.clear(user_id)

    # ################ 订阅开关 ################

    async def get_subscriptions(self, user_id: str) -> list[ContactSubscriptionResponse]:
        """订阅矩阵: 通知类型 x 外部通道 展开的当前开关状态"""
        rows: dict[str, dict[str, bool]] = {}
        for row in await self.subscription_dao.list_for_user(user_id=user_id):
            rows.setdefault(row.notify_type, {})[row.channel] = row.enabled
        result = []
        for type_def in NOTIFY_TYPES:
            channel_states = rows.get(type_def["type_code"], {})
            for channel in EXTERNAL_CHANNELS:
                result.append(
                    ContactSubscriptionResponse(
                        notify_type=type_def["type_code"],
                        type_name=type_def["type_name"],
                        channel=channel,
                        enabled=bool(channel_states.get(channel, False)),
                    )
                )
        return result

    async def set_subscription(
        self, user_id: str, notify_type: str, channel: str, enabled: bool
    ) -> ContactSubscriptionResponse:
        """
        设置订阅开关(记录级 upsert)
        :raises BusinessError: 通知类型或通道非法
        """
        if not any(t["type_code"] == notify_type for t in NOTIFY_TYPES):
            raise BusinessError(f"通知类型 {notify_type} 未注册")
        if channel not in EXTERNAL_CHANNELS:
            raise BusinessError(f"通道 {channel} 非法(仅支持 {'/'.join(EXTERNAL_CHANNELS)})")
        await self.subscription_dao.upsert(user_id, notify_type, channel, enabled)
        type_name = next(t["type_name"] for t in NOTIFY_TYPES if t["type_code"] == notify_type)
        return ContactSubscriptionResponse(
            notify_type=notify_type, type_name=type_name, channel=channel, enabled=enabled
        )


# 全局单例(无状态, 复用避免重复构造; 通知埋点跨模块调用)
_notification_service = NotificationService(
    ContactMessageDao(), ContactSubscriptionDao()
)


def get_notification_service() -> NotificationService:
    """NotificationService 依赖注入工厂(FastAPI Depends 使用)"""
    return _notification_service
