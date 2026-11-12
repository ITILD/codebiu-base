"""AI 能力平台批次 2(REQ-018): 自定义 Skill 归属列

- ai_skill + owner_user_id(prompt 自定义 Skill 创建者; 内置为空)

Revision ID: 0004_skill_owner
Revises: 0003_ai_capability_platform
Create Date: 2026-11-11
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_skill_owner"
down_revision: str | None = "0003_ai_capability_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if "owner_user_id" not in _columns("ai_skill"):
        op.add_column(
            "ai_skill",
            sa.Column("owner_user_id", sa.String(length=50), nullable=True),
        )
        op.create_index("ix_ai_skill_owner", "ai_skill", ["owner_user_id"], unique=False)


def downgrade() -> None:
    if "owner_user_id" in _columns("ai_skill"):
        op.drop_index("ix_ai_skill_owner", table_name="ai_skill")
        op.drop_column("ai_skill", "owner_user_id")
