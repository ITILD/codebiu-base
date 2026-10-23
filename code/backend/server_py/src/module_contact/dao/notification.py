"""通知中心数据访问层(REQ-011): 站内信 CRUD 与用户订阅开关"""

from sqlmodel import delete, func, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from common.utils.fastapi_ex.exceptions import NotFoundError
from common.utils.db.schema.pagination import PaginationParams
from module_contact.do.notification import (
    EXTERNAL_CHANNELS,
    ContactMessage,
    ContactSubscription,
)


class ContactMessageDao:
    @DaoRel
    async def add(self, data: ContactMessage, session: AsyncSession | None = None) -> int:
        """新增站内信 :return: 自增主键"""
        session.add(data)
        await session.flush()
        return data.id  # type: ignore[return-value]

    @DaoRel
    async def get(
        self, message_id: int, user_id: str, session: AsyncSession | None = None
    ) -> ContactMessage | None:
        """按ID查询(仅本人可见, 防越权读写)"""
        statement = select(ContactMessage).where(
            ContactMessage.id == message_id, ContactMessage.user_id == user_id
        )
        return (await session.exec(statement)).first()

    @DaoRel
    async def list_page(
        self,
        pagination: PaginationParams,
        user_id: str,
        session: AsyncSession | None = None,
        is_read: bool | None = None,
    ) -> list[ContactMessage]:
        """分页查询当前用户站内信(时间倒序)"""
        statement = select(ContactMessage).where(ContactMessage.user_id == user_id)
        if is_read is not None:
            statement = statement.where(ContactMessage.is_read == is_read)
        statement = (
            statement.order_by(ContactMessage.id.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        return list((await session.exec(statement)).all())

    @DaoRel
    async def count(
        self,
        user_id: str,
        session: AsyncSession | None = None,
        is_read: bool | None = None,
    ) -> int:
        """统计当前用户站内信数(与列表过滤条件一致)"""
        statement = select(func.count()).select_from(ContactMessage).where(
            ContactMessage.user_id == user_id
        )
        if is_read is not None:
            statement = statement.where(ContactMessage.is_read == is_read)
        return (await session.exec(statement)).one()

    @DaoRel
    async def mark_read(
        self, message_id: int, user_id: str, session: AsyncSession | None = None
    ) -> None:
        """标记单条已读(仅本人记录可标记)"""
        message = await self.get(message_id, user_id, session=session)  # type: ignore[arg-type]
        if not message:
            raise NotFoundError(f"未找到ID为 {message_id} 的通知")
        message.is_read = True
        session.add(message)
        await session.flush()

    @DaoRel
    async def mark_all_read(self, user_id: str, session: AsyncSession | None = None) -> int:
        """全部已读(单条 UPDATE, 避免全量加载后逐行标记) :return: 标记条数"""
        statement = (
            update(ContactMessage)
            .where(
                ContactMessage.user_id == user_id,
                ContactMessage.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        result = await session.exec(statement)
        await session.flush()
        return result.rowcount

    @DaoRel
    async def clear(self, user_id: str, session: AsyncSession | None = None) -> None:
        """清空当前用户全部站内信(单条 DELETE, 含已读)"""
        statement = delete(ContactMessage).where(ContactMessage.user_id == user_id)
        await session.exec(statement)
        await session.flush()


class ContactSubscriptionDao:
    @DaoRel
    async def list_for_user(
        self, user_id: str, session: AsyncSession | None = None, notify_type: str | None = None
    ) -> list[ContactSubscription]:
        """查询用户订阅记录(可按通知类型过滤)"""
        statement = select(ContactSubscription).where(ContactSubscription.user_id == user_id)
        if notify_type:
            statement = statement.where(ContactSubscription.notify_type == notify_type)
        return list((await session.exec(statement)).all())

    @DaoRel
    async def upsert(
        self,
        user_id: str,
        notify_type: str,
        channel: str,
        enabled: bool,
        session: AsyncSession | None = None,
    ) -> ContactSubscription:
        """设置订阅开关(记录存在则更新, 不存在则新建)"""
        statement = select(ContactSubscription).where(
            ContactSubscription.user_id == user_id,
            ContactSubscription.notify_type == notify_type,
            ContactSubscription.channel == channel,
        )
        row = (await session.exec(statement)).first()
        if row is None:
            row = ContactSubscription(user_id=user_id, notify_type=notify_type, channel=channel)
        row.enabled = enabled
        session.add(row)
        await session.flush()
        return row

    @DaoRel
    async def delete_for_user(self, user_id: str, session: AsyncSession | None = None) -> None:
        """删除用户全部订阅记录(单条 DELETE, 测试清理用)"""
        statement = delete(ContactSubscription).where(ContactSubscription.user_id == user_id)
        await session.exec(statement)
        await session.flush()


# 非法通道校验用(与 service 共享)
VALID_CHANNELS: tuple[str, ...] = EXTERNAL_CHANNELS
