"""agent_configs: declarative governance columns

Revision ID: 026_agent_governance
Revises: 025_kill_switch
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "026_agent_governance"
down_revision = "025_kill_switch"
branch_labels = None
depends_on = None

_COLUMNS = {
    "autonomy_tier": sa.Column("autonomy_tier", sa.String(8), nullable=False, server_default="L2"),
    "l3_authorization_ref": sa.Column("l3_authorization_ref", sa.String(255), nullable=True),
    "allowed_categories": sa.Column("allowed_categories", sa.JSON(), nullable=True),
    "auto_execute_min_confidence": sa.Column("auto_execute_min_confidence", sa.Float(), nullable=False, server_default="0.85"),
    "escalate_to_human_below": sa.Column("escalate_to_human_below", sa.Float(), nullable=False, server_default="0.60"),
    "pii_handling_policy": sa.Column("pii_handling_policy", sa.String(20), nullable=False, server_default="redact"),
    "kill_switch_enabled": sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False, server_default="true"),
    "is_poc": sa.Column("is_poc", sa.Boolean(), nullable=False, server_default="true"),
    "requires_approval_rules": sa.Column("requires_approval_rules", sa.JSON(), nullable=True),
}


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_configs")}


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("agent_configs", column)


def downgrade() -> None:
    existing = _existing()
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("agent_configs", name)
