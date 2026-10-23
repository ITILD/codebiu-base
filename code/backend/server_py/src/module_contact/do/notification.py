"""通知中心 contact_message / contact_subscription 表模型与请求/响应体定义(REQ-011)

- 站内信必达: notify 调用总是写入 contact_message 一条记录
- 外部通道(email/sms)按用户订阅开关路由, 联系方式缺失时自动降级站内
- 通知类型字典化: NOTIFY_TYPES 单一来源, 字典种子(module_contact/config/dict_seed.py)
  从本常量派生, 保证字典与代码不漂移
"""

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ################ 通道与通知类型常量 ################

# 通知通道
CHANNEL_INAPP = "inapp"  # 站内信(必达, 无订阅开关)
CHANNEL_EMAIL = "email"  # 邮件(按订阅路由)
CHANNEL_SMS = "sms"  # 短信(按订阅路由)
# 外部通道集合(订阅矩阵按此展开)
EXTERNAL_CHANNELS: tuple[str, ...] = (CHANNEL_EMAIL, CHANNEL_SMS)

# 通知类型字典(单一来源: 前端订阅矩阵/字典种子/埋点编码共用)
NOTIFY_TYPES: list[dict[str, str]] = [
    {"type_code": "task_done", "type_name": "任务执行结果", "description": "后台任务成功/失败终态提醒"},
]


class ContactMessage(SQLModel, table=True):
    """站内信表(通知必达落库, 前端铃铛按未读数轮询拉取)"""

    __tablename__ = "contact_message"
    __table_args__ = (
        # 未读数/列表主查询路径: 按用户过滤 + 已读过滤, 无全表扫描
        Index("ix_contact_message_user_read", "user_id", "is_read"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, description="收件人用户ID")
    notify_type: str = Field(
        max_length=50, description="通知类型编码(NOTIFY_TYPES/字典 contact_notify_type)"
    )
    title: str = Field(max_length=200, description="通知标题")
    content: str | None = Field(
        default=None, sa_column=Column(Text), description="通知正文(可空, 如失败原因)"
    )
    channels: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
        description="实际尝试送达的通道快照(如 [\"inapp\",\"email\"]; 外部失败仅日志不回改)",
    )
    is_read: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
        description="已读标记",
    )
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))


class ContactSubscription(SQLModel, table=True):
    """用户通知订阅开关表(按 通知类型 x 外部通道 一行; 站内信必达无开关)

    未落记录视为未订阅(默认关闭, 防止配置短信/邮件后全员群发产生费用);
    用户在前端通知中心显式开启。
    """

    __tablename__ = "contact_subscription"
    __table_args__ = (
        # upsert 查重路径: 用户+类型+通道 唯一
        UniqueConstraint("user_id", "notify_type", "channel", name="uq_contact_subscription"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, description="用户ID")
    notify_type: str = Field(max_length=50, description="通知类型编码")
    channel: str = Field(
        sa_column=Column(String(20)), description="外部通道(email/sms; 站内信必达不建开关)"
    )
    enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
        description="是否订阅",
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), onupdate=_utcnow, nullable=False),
    )


# ################ 请求/响应体 ################

class ContactMessageResponse(SQLModel):
    """站内信响应(前端铃铛列表)"""

    id: int
    notify_type: str
    title: str
    content: str | None = None
    channels: list = []
    is_read: bool
    created_at: datetime


class ContactSubscriptionResponse(SQLModel):
    """订阅矩阵单项(通知类型 x 通道 展开后的当前开关状态)"""

    notify_type: str
    type_name: str
    channel: str
    enabled: bool


class ContactSubscriptionUpdate(SQLModel):
    """订阅开关设置请求"""

    notify_type: str = Field(max_length=50, description="通知类型编码")
    channel: str = Field(max_length=20, description="外部通道(email/sms)")
    enabled: bool = Field(description="是否订阅")
