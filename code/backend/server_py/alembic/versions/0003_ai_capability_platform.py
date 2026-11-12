"""AI 能力平台(REQ-018): Skill 资产/调用观测/Agent job 表 + 既有表扩展

新增:
- ai_skill / ai_skill_version   Skill 资产登记与版本快照
- skill_invocation              统一调用观测(三入口/两形态)
- agent_job_run                 static_agent 批处理 job 载体(W-3)
扩展:
- agent_agent                   + agent_kind/decision_mode/steps/execution_strategy
- task_queue                    + invocation_id(与 skill_invocation 双向关联)

Revision ID: 0003_ai_capability_platform
Revises: 0002_user_preference
Create Date: 2026-11-11
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0003_ai_capability_platform"
down_revision: str | None = "0002_user_preference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _table_names()

    # ---- 新表(启动期 create_all 可能已建表, 幂等保护) ----
    if "ai_skill" not in existing:
        op.create_table(
            "ai_skill",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("namespace", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("category", sa.String(length=30), nullable=False),
            sa.Column("skill_type", sa.String(length=30), nullable=False),
            sa.Column("nature", sa.String(length=10), nullable=False),
            sa.Column("origin", sa.String(length=30), nullable=False),
            sa.Column("origin_version", sa.String(length=60), nullable=False),
            sa.Column("current_version", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("deprecated", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ai_skill_id", "ai_skill", ["id"], unique=False)
        op.create_index("ix_ai_skill_key", "ai_skill", ["key"], unique=False)
        op.create_index("ix_ai_skill_key_unique", "ai_skill", ["key"], unique=True)

    if "ai_skill_version" not in existing:
        op.create_table(
            "ai_skill_version",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("skill_id", sa.String(), nullable=False),
            sa.Column("version", sa.String(length=30), nullable=False),
            sa.Column("config_hash", sa.String(length=64), nullable=False),
            sa.Column("manifest_snapshot", JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ai_skill_version_id", "ai_skill_version", ["id"], unique=False)
        op.create_index("ix_ai_skill_version_skill", "ai_skill_version", ["skill_id", "version"], unique=False)
        op.create_index("ix_ai_skill_version_config_hash", "ai_skill_version", ["config_hash"], unique=False)

    if "skill_invocation" not in existing:
        op.create_table(
            "skill_invocation",
            sa.Column("invocation_id", sa.String(), nullable=False),
            sa.Column("skill_key", sa.String(length=120), nullable=False),
            sa.Column("skill_version", sa.String(length=30), nullable=False),
            sa.Column("mode", sa.String(length=10), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("priority_class", sa.String(length=20), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("input_summary", JSONB(), nullable=False),
            sa.Column("output", JSONB(), nullable=True),
            sa.Column("degraded", sa.Boolean(), nullable=False),
            sa.Column("error_class", sa.String(length=30), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("tokens", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=True),
            sa.Column("entry", sa.String(length=30), nullable=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("invocation_id"),
        )
        op.create_index("ix_skill_invocation_invocation_id", "skill_invocation", ["invocation_id"], unique=False)
        op.create_index("ix_skill_invocation_idempotency_key", "skill_invocation", ["idempotency_key"], unique=False)
        op.create_index("ix_skill_invocation_skill_created", "skill_invocation", ["skill_key", "created_at"], unique=False)
        op.create_index("ix_skill_invocation_user", "skill_invocation", ["user_id"], unique=False)
        op.create_index("ix_skill_invocation_task", "skill_invocation", ["task_id"], unique=False)

    if "agent_job_run" not in existing:
        op.create_table(
            "agent_job_run",
            sa.Column("job_run_id", sa.String(), nullable=False),
            sa.Column("agent_key", sa.String(length=120), nullable=False),
            sa.Column("agent_version", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("priority_class", sa.String(length=20), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("input_summary", JSONB(), nullable=False),
            sa.Column("progress", JSONB(), nullable=False),
            sa.Column("steps_state", JSONB(), nullable=False),
            sa.Column("checkpoint", JSONB(), nullable=False),
            sa.Column("result", JSONB(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("task_id", sa.String(length=64), nullable=True),
            sa.Column("entry", sa.String(length=30), nullable=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("job_run_id"),
        )
        op.create_index("ix_agent_job_run_job_run_id", "agent_job_run", ["job_run_id"], unique=False)
        op.create_index("ix_agent_job_run_idempotency_key", "agent_job_run", ["idempotency_key"], unique=False)
        op.create_index("ix_agent_job_run_agent_created", "agent_job_run", ["agent_key", "created_at"], unique=False)
        op.create_index("ix_agent_job_run_user", "agent_job_run", ["user_id"], unique=False)
        op.create_index("ix_agent_job_run_task", "agent_job_run", ["task_id"], unique=False)

    # ---- 既有表扩展 ----
    agent_cols = _columns("agent_agent")
    if "agent_kind" not in agent_cols:
        op.add_column(
            "agent_agent",
            sa.Column("agent_kind", sa.String(length=10), nullable=False, server_default="chat"),
        )
    if "decision_mode" not in agent_cols:
        op.add_column(
            "agent_agent",
            sa.Column("decision_mode", sa.String(length=10), nullable=False, server_default="model"),
        )
    if "steps" not in agent_cols:
        op.add_column("agent_agent", sa.Column("steps", JSONB(), nullable=True))
    if "execution_strategy" not in agent_cols:
        op.add_column("agent_agent", sa.Column("execution_strategy", sa.String(length=20), nullable=True))

    task_cols = _columns("task_queue")
    if "invocation_id" not in task_cols:
        op.add_column("task_queue", sa.Column("invocation_id", sa.String(length=64), nullable=True))
        op.create_index("ix_task_queue_invocation_id", "task_queue", ["invocation_id"], unique=False)


def downgrade() -> None:
    existing = _table_names()
    if "task_queue" in existing and "invocation_id" in _columns("task_queue"):
        op.drop_index("ix_task_queue_invocation_id", table_name="task_queue")
        op.drop_column("task_queue", "invocation_id")
    if "agent_agent" in existing:
        for col in ("execution_strategy", "steps", "decision_mode", "agent_kind"):
            if col in _columns("agent_agent"):
                op.drop_column("agent_agent", col)
    for table, indexes in (
        ("agent_job_run", ("ix_agent_job_run_task", "ix_agent_job_run_user", "ix_agent_job_run_agent_created", "ix_agent_job_run_idempotency_key", "ix_agent_job_run_job_run_id")),
        ("skill_invocation", ("ix_skill_invocation_task", "ix_skill_invocation_user", "ix_skill_invocation_skill_created", "ix_skill_invocation_idempotency_key", "ix_skill_invocation_invocation_id")),
        ("ai_skill_version", ("ix_ai_skill_version_config_hash", "ix_ai_skill_version_skill", "ix_ai_skill_version_id")),
        ("ai_skill", ("ix_ai_skill_key_unique", "ix_ai_skill_key", "ix_ai_skill_id")),
    ):
        if table in existing:
            for idx in indexes:
                op.drop_index(idx, table_name=table)
            op.drop_table(table)
