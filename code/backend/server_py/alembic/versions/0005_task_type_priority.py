"""任务类型优先级热调表(运维不改代码即可调整某类任务入队优先级)

Revision ID: 0005_task_type_priority
Revises: 0004_skill_owner
Create Date: 2026-11-15

- 新表 task_type_priority: task_type(主键) → priority_override, updated_at
- 同一类型仅一条记录; 删除记录即回落注册表默认优先级
- 仅影响"之后创建"的任务; 已入队任务不变
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_task_type_priority"
down_revision = "0004_skill_owner"
branch_labels = None
depends_on = None

_TABLE = "task_type_priority"


def _table_exists(table_name: str) -> bool:
    """幂等检查: 表已存在则跳过(本地/测试环境可能已 create_all)"""
    conn = op.get_bind()
    return sa.inspect(conn).has_table(table_name)


def upgrade() -> None:
    if _table_exists(_TABLE):
        print(f"[0005] 表 {_TABLE} 已存在, 跳过创建")
        return
    op.create_table(
        _TABLE,
        sa.Column(
            "task_type",
            sa.String(length=50),
            primary_key=True,
            comment="任务类型编码(对应 TASK_TYPES 注册表)",
        ),
        sa.Column(
            "priority_override",
            sa.Integer(),
            nullable=False,
            comment="覆盖后的入队优先级(0~9, 越大越优先)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="最后调整时间",
        ),
        comment="任务类型入队优先级覆盖(运维热调)",
    )


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    op.drop_table(_TABLE)
