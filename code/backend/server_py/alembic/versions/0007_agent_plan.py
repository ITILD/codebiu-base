"""五拍协议清单投影与事件日志落库(REQ-019 批次 5)

Revision ID: 0007_agent_plan
Revises: 0006_agent_chat_modes
Create Date: 2026-11-17

- 新表 agent_plan_item: 清单投影 + 验收事实(verdict_*)载体
- 新表 agent_plan_event: 事件日志(系统事实源, write_plan/submit/verdict/revise/...)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007_agent_plan"
down_revision = "0006_agent_chat_modes"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return inspector.has_table(table_name)


def upgrade() -> None:
    if _table_exists("agent_plan_item"):
        print("[0007] agent_plan_item 已存在, 跳过建表")
    else:
        op.create_table(
            "agent_plan_item",
            sa.Column("id", sa.String(), primary_key=True, index=True),
            sa.Column("run_id", sa.String(64), nullable=False, comment="五拍协议运行实例ID"),
            sa.Column("item_id", sa.String(64), nullable=False, comment="清单项ID"),
            sa.Column("goal", sa.Text(), nullable=False, comment="任务目标"),
            sa.Column("acceptance_kind", sa.String(20), nullable=False, comment="验收类型"),
            sa.Column("acceptance_spec", sa.Text(), nullable=False, comment="验收标准"),
            sa.Column("acceptance_hash", sa.String(32), nullable=True, comment="验收标准指纹(防削弱)"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_reason", sa.Text(), nullable=True),
            sa.Column("verdict_passed", sa.Boolean(), nullable=True, comment="验收事实(假完成率统计)"),
            sa.Column("verdict_reason", sa.Text(), nullable=True),
            sa.Column("conversation_id", sa.String(64), nullable=True),
            sa.Column("user_id", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_plan_item_run", "agent_plan_item", ["run_id", "item_id"])
        op.create_index("ix_agent_plan_item_conversation", "agent_plan_item", ["conversation_id"])

    if _table_exists("agent_plan_event"):
        print("[0007] agent_plan_event 已存在, 跳过建表")
    else:
        op.create_table(
            "agent_plan_event",
            sa.Column("id", sa.String(), primary_key=True, index=True),
            sa.Column("run_id", sa.String(64), nullable=False, comment="五拍协议运行实例ID"),
            sa.Column("event_type", sa.String(40), nullable=False, comment="事件类型"),
            sa.Column("item_id", sa.String(64), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("conversation_id", sa.String(64), nullable=True),
            sa.Column("user_id", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_plan_event_run", "agent_plan_event", ["run_id", "created_at"])


def downgrade() -> None:
    if _table_exists("agent_plan_event"):
        op.drop_index("ix_agent_plan_event_run", table_name="agent_plan_event")
        op.drop_table("agent_plan_event")
    if _table_exists("agent_plan_item"):
        op.drop_index("ix_agent_plan_item_conversation", table_name="agent_plan_item")
        op.drop_index("ix_agent_plan_item_run", table_name="agent_plan_item")
        op.drop_table("agent_plan_item")
