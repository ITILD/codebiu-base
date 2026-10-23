"""系统主模块 操作审计日志表模型(REQ-009)"""

from sqlmodel import Column, DateTime, Field, SQLModel
from uuid import uuid4
from datetime import datetime, timezone


class AuditLog(SQLModel, table=True):
    """操作审计日志数据库模型(只写不改: 由中间件批量插入)"""

    __tablename__ = "sys_audit_log"

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        primary_key=True,
        index=True,
        description="唯一标识符",
    )
    user_id: str | None = Field(default=None, index=True, description="操作用户ID(匿名请求为空)")
    username: str | None = Field(default=None, index=True, description="操作用户名(登录请求取表单用户名)")
    method: str = Field(max_length=10, index=True, description="HTTP 方法")
    path: str = Field(max_length=500, index=True, description="请求路径")
    params_digest: str | None = Field(default=None, max_length=2000, description="请求参数摘要(敏感字段已脱敏)")
    status_code: int = Field(description="响应状态码")
    duration_ms: float = Field(default=0, description="耗时(毫秒)")
    ip: str | None = Field(default=None, max_length=64, description="客户端IP(优先 X-Forwarded-For)")
    user_agent: str | None = Field(default=None, max_length=500, description="User-Agent")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
        description="记录时间",
    )
