"""Agent job 执行实例表(REQ-018, W-3 设计内建不后置)

agent_job_run 是 static_agent 批处理编排的观测/幂等/断点载体:
- Agent 级幂等: 同 idempotency_key 的活跃 job 重复提交直接复用
- 步骤状态: steps_state 记录每个 step 每个展开项的状态与 when/skip_if 判定结果
- 断点续跑: checkpoint 记录执行位置(全链路续跑能力批次 2 交付, 载体先行内建)
"""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class JobRunStatus(StrEnum):
    """job 生命周期"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentJobRun(SQLModel, table=True):
    """Agent job 执行实例(static_agent 的每次运行)"""

    __tablename__ = "agent_job_run"
    __table_args__ = (
        Index("ix_agent_job_run_agent_created", "agent_key", "created_at"),
        Index("ix_agent_job_run_user", "user_id"),
        Index("ix_agent_job_run_task", "task_id"),
    )

    job_run_id: str = Field(
        default_factory=lambda: uuid4().hex, primary_key=True, index=True,
        description="job 运行唯一标识",
    )
    agent_key: str = Field(max_length=120, description="Agent 键(如 sys.kb_ingest_agent)")
    agent_version: str = Field(default="1", max_length=30, description="Agent 步骤声明版本")
    status: str = Field(
        default=JobRunStatus.PENDING,
        sa_column=Column(String(20), nullable=False, default=JobRunStatus.PENDING),
    )
    priority_class: str = Field(default="batch", max_length=20, description="优先级类")
    # Agent 级幂等指纹(同 job+业务键重复提交去重)
    idempotency_key: str | None = Field(
        default=None, max_length=128, index=True, description="幂等指纹(agent_key+业务键)",
    )
    input_summary: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False),
        description="输入摘要(文档数/项目ID等, 不存大产物)",
    )
    progress: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False),
        description="进度汇总 {total, succeeded, failed, skipped, percent}",
    )
    steps_state: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False),
        description="步骤状态: {step_id: {status, when/skip_if 判定, 展开项明细, 关联 invocation}}",
    )
    checkpoint: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False),
        description="断点检查点(执行位置; 断点续跑全链路批次 2, 载体内建 W-3)",
    )
    result: dict | None = Field(default=None, sa_column=Column(JSONB), description="聚合结果摘要")
    error: str | None = Field(default=None, sa_column=Column(Text), description="失败原因")
    task_id: str | None = Field(default=None, index=True, max_length=64, description="关联 task_queue.id")
    entry: str | None = Field(default=None, max_length=30, description="触发入口: web/agent/task")
    user_id: str = Field(index=True, description="提交者用户ID")
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
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
