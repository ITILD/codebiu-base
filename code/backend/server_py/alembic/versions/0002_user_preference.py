"""新增 user_preference 用户样式偏好表

每个用户保存一条界面样式偏好(主题模式), 登录后前端据此套用对应主题。

Revision ID: 0002_user_preference
Revises: 0001_baseline
Create Date: 2026-10-24
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_user_preference"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "user_preference"


def upgrade() -> None:
    """创建用户样式偏好表(启动期 create_all 可能已建表, 此处做幂等保护)"""
    if TABLE_NAME in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("theme", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(f"ix_{TABLE_NAME}_id", TABLE_NAME, ["id"], unique=False)
    op.create_index(
        f"ix_{TABLE_NAME}_user_id", TABLE_NAME, ["user_id"], unique=True
    )


def downgrade() -> None:
    """删除用户样式偏好表"""
    op.drop_index(f"ix_{TABLE_NAME}_user_id", table_name=TABLE_NAME)
    op.drop_index(f"ix_{TABLE_NAME}_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
