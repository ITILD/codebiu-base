"""skill_invocation 增加 agent_run_id / mode_budget_hit(REQ-019 设计 §7)

Revision ID: 0008_skill_inv_agent_run
Revises: 0007_agent_plan
Create Date: 2026-11-17

- agent_run_id: 五拍协议运行实例ID(五拍协议调用经 SkillRuntime 留痕的关联键)
- mode_budget_hit: 预算触顶标记(北极星恶化时的下钻维度)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0008_skill_inv_agent_run"
down_revision = "0007_agent_plan"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    cols = _columns("skill_invocation")
    if "agent_run_id" not in cols:
        op.add_column(
            "skill_invocation",
            sa.Column(
                "agent_run_id", sa.String(64), nullable=True,
                comment="五拍协议运行实例ID(REQ-019 §7: 关联 Agent 运行实例)",
            ),
        )
        op.create_index("ix_skill_invocation_agent_run_id", "skill_invocation", ["agent_run_id"])
    else:
        print("[0008] skill_invocation.agent_run_id 已存在, 跳过")

    if "mode_budget_hit" not in cols:
        op.add_column(
            "skill_invocation",
            sa.Column(
                "mode_budget_hit", sa.Boolean(), nullable=False, server_default=sa.false(),
                comment="预算触顶标记(§7: 该调用所属运行是否触顶)",
            ),
        )
    else:
        print("[0008] skill_invocation.mode_budget_hit 已存在, 跳过")


def downgrade() -> None:
    cols = _columns("skill_invocation")
    if "mode_budget_hit" in cols:
        op.drop_column("skill_invocation", "mode_budget_hit")
    if "agent_run_id" in cols:
        op.drop_index("ix_skill_invocation_agent_run_id", table_name="skill_invocation")
        op.drop_column("skill_invocation", "agent_run_id")
