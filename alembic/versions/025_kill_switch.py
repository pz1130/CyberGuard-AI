"""kill_switch_state table

Revision ID: 025_kill_switch
Revises: 024_action_taxonomy
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "025_kill_switch"
down_revision = "024_action_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "kill_switch_state" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "kill_switch_state",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("scope", sa.String(64), nullable=False, unique=True),
            sa.Column("engaged_by", sa.String(255), nullable=True),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("engaged_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_kill_switch_scope", "kill_switch_state", ["scope"])


def downgrade() -> None:
    if "kill_switch_state" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_kill_switch_scope", table_name="kill_switch_state")
        op.drop_table("kill_switch_state")
