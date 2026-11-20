"""问答用量记录表模型与响应体(成本与用量治理数据底座)

每轮问答落一条记录:
- token 数在回答完成时统计快照(输入含 system prompt 与历史消息)
- cost 按当次模型单价快照计算(pay_in/pay_out 口径: 元/百万token),
  后续单价调整不影响历史记录
"""
from pydantic import BaseModel
from sqlmodel import Column, DateTime, Field, SQLModel
from uuid import uuid4
from datetime import datetime, timezone


class ChatUsage(SQLModel, table=True):
    """问答用量数据库模型"""

    __tablename__ = "chat_usage"

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        primary_key=True,
        index=True,
        description="唯一标识符",
    )
    user_id: str = Field(..., max_length=50, index=True, description="发起用户ID")
    conversation_id: str = Field(
        ..., max_length=50, index=True, description="所属对话ID"
    )
    agent_id: str | None = Field(default=None, max_length=50, description="智能体ID")
    # 回答使用的模型标识(model_config.model), 旁路记录失败时可能为空
    model_name: str | None = Field(default=None, max_length=200, description="模型标识")
    # 执行模式: fast/thinking/deep
    mode: str = Field(default="", max_length=20, description="执行模式")
    prompt_tokens: int = Field(default=0, description="输入token数")
    completion_tokens: int = Field(default=0, description="输出token数")
    # 成本快照(元, 按写入时单价计算; 未配置单价的模型为 0)
    cost: float = Field(default=0.0, description="成本快照(元)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
        description="创建时间",
    )


class UsageRecordItem(BaseModel):
    """用量明细条目(补齐用户名展示)"""

    id: str
    user_id: str
    username: str | None = None
    nickname: str | None = None
    conversation_id: str
    agent_id: str | None = None
    model_name: str | None = None
    mode: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    created_at: datetime


class UsageConversationItem(BaseModel):
    """对话维度用量聚合条目(管理员对话记录列表)"""

    conversation_id: str
    title: str | None = None
    user_id: str
    username: str | None = None
    nickname: str | None = None
    rounds: int = 0  # 问答轮次(用量记录条数)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    last_active_at: datetime | None = None
