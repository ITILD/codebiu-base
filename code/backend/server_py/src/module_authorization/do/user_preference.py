"""权限认证模块 user_preference 表模型与请求/响应体定义(用户样式偏好)"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Column, DateTime, Field, SQLModel

# 允许的主题模式: auto=跟随系统 / light=亮色 / dark=暗色
THEME_MODES: tuple[str, ...] = ("auto", "light", "dark")


class UserPreferenceBase(SQLModel):
    """用户样式偏好基础模型(不含数据库表配置)"""

    theme: str = Field(
        default="auto", max_length=10, description="主题模式: auto/light/dark"
    )


class UserPreference(UserPreferenceBase, table=True):
    """用户样式偏好数据库模型(每个用户一条记录)"""

    __tablename__ = "user_preference"

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        primary_key=True,
        index=True,
        description="唯一标识符",
    )
    user_id: str = Field(
        ..., unique=True, index=True, description="用户ID(一个用户仅一条偏好)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="创建时间",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
        description="最后更新时间",
    )


class UserPreferenceUpdate(SQLModel):
    """更新用户样式偏好的请求模型"""

    theme: str = Field(..., max_length=10, description="主题模式: auto/light/dark")


class UserPreferenceResponse(SQLModel):
    """用户样式偏好响应模型"""

    theme: str = Field(default="auto", description="主题模式: auto/light/dark")
