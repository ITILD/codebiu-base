"""五拍协议清单投影与事件日志表(REQ-019 设计 §4.8/§7, FEAT-AICAP-016)

- agent_plan_item: 清单投影(模型事实源是 checkpointer/内存, 本表是 UI 投影 + 验收事实载体);
  验收事实落 verdict_passed / verdict_reason, 支撑北极星「假完成率」统计。
- agent_plan_event: 事件日志(系统事实源): write_plan / write_plan_rejected / submit /
  verdict / revise / experience / guard_stop, 供回放、审计、恢复。

> 系统的事实源是日志, 模型的事实源是清单(日志的投影); 两者只需单向投影, 不需要同步协议。
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AgentPlanItem(SQLModel, table=True):
    """清单项投影(任务型 ai_agent 五拍协议)"""

    __tablename__ = "agent_plan_item"
    __table_args__ = (
        Index("ix_agent_plan_item_run", "run_id", "item_id"),
        Index("ix_agent_plan_item_conversation", "conversation_id"),
    )

    id: str = Field(
        default_factory=lambda: uuid4().hex, primary_key=True, index=True,
        description="投影行唯一标识",
    )
    run_id: str = Field(max_length=64, description="五拍协议运行实例ID")
    item_id: str = Field(max_length=64, description="清单项ID(模型 write_plan 声明)")
    goal: str = Field(sa_column=Column(Text, nullable=False), description="任务目标")
    acceptance_kind: str = Field(max_length=20, description="验收类型 cmd/artifact/judge/human")
    acceptance_spec: str = Field(sa_column=Column(Text, nullable=False), description="验收标准")
    acceptance_hash: str = Field(default="", max_length=32, description="验收标准指纹(防削弱)")
    status: str = Field(default="pending", max_length=20, description="pending/done")
    attempts: int = Field(default=0, description="交卷尝试次数")
    last_reason: str = Field(default="", sa_column=Column(Text), description="上次失败原因")
    verdict_passed: bool | None = Field(default=None, description="验收事实(假完成率统计)")
    verdict_reason: str = Field(default="", sa_column=Column(Text), description="验收裁决原因")
    conversation_id: str = Field(default="", max_length=64, index=True, description="关联会话")
    user_id: str = Field(default="", max_length=50, index=True, description="归属用户")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
    )


class AgentPlanEvent(SQLModel, table=True):
    """五拍协议事件日志(系统事实源)"""

    __tablename__ = "agent_plan_event"
    __table_args__ = (Index("ix_agent_plan_event_run", "run_id", "created_at"),)

    id: str = Field(
        default_factory=lambda: uuid4().hex, primary_key=True, index=True,
        description="事件唯一标识",
    )
    run_id: str = Field(max_length=64, description="五拍协议运行实例ID")
    event_type: str = Field(
        max_length=40,
        description="write_plan/write_plan_rejected/submit/verdict/revise/experience/guard_stop",
    )
    item_id: str = Field(default="", max_length=64, description="关联清单项ID(可为空)")
    payload: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False),
        description="事件负载(不存大产物, 产物只存路径)",
    )
    conversation_id: str = Field(default="", max_length=64, description="关联会话")
    user_id: str = Field(default="", max_length=50, description="归属用户")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
