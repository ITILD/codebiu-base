"""基线版本: v1.0.0 create_all 全量结构

空迁移(无 DDL): 全新库由主服务首启 create_all 直接建全量表, 随后自动 stamp 到本版本;
此后所有结构变更以本版本为起点, `alembic revision --autogenerate` 生成增量脚本。
存量库接入迁移: 先 `alembic stamp head` 打标, 再随版本演进 `alembic upgrade head`。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-20
"""
from __future__ import annotations

from typing import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """基线无 DDL(全量结构由 create_all 建立)"""
    pass


def downgrade() -> None:
    """基线不可降级(降级即回到空库, 等价 drop_all, 不提供)"""
    pass
