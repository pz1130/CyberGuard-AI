"""agent_configs: governed (wrapped) flag

Revision ID: 031_agent_governed_flag
Revises: 030_audit_worm_exports
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "031_agent_governed_flag"
down_revision = "030_audit_worm_exports"
branch_labels = None
depends_on = None


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_configs")}


def upgrade() -> None:
    if "governed" not in _existing():
        op.add_column("agent_configs",
                      sa.Column("governed", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    if "governed" in _existing():
        op.drop_column("agent_configs", "governed")
