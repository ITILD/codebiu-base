"""对话模式配置落库(模式即 Agent, REQ-019)

Revision ID: 0006_agent_chat_modes
Revises: 0005_task_type_priority
Create Date: 2026-11-17

- agent_agent 增列 chat_modes(JSON): {模式名: 运行参数}
- 内置对话 Agent(builtin_fast / builtin_thinking)以代码 Manifest 为事实源只读同步
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_agent_chat_modes"
down_revision = "0005_task_type_priority"
branch_labels = None
depends_on = None

_TABLE = "agent_agent"
_COLUMN = "chat_modes"


def _column_exists(table_name: str, column_name: str) -> bool:
    """幂等检查: 列已存在则跳过(本地/测试环境可能已 create_all)"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    if _column_exists(_TABLE, _COLUMN):
        print(f"[0006] 列 {_TABLE}.{_COLUMN} 已存在, 跳过新增")
        return
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.JSON(),
            nullable=True,
            comment="对话模式配置 {模式名: 运行参数}(内置对话 Agent 只读同步)",
        ),
    )


def downgrade() -> None:
    if not _column_exists(_TABLE, _COLUMN):
        return
    op.drop_column(_TABLE, _COLUMN)
