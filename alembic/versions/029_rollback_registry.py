"""rollback_registrations table (Safety Envelope)

Revision ID: 029_rollback_registry
Revises: 028_tool_safety_envelope
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "029_rollback_registry"
down_revision = "028_tool_safety_envelope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "rollback_registrations" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "rollback_registrations",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("action_id", sa.String(36), nullable=False, unique=True),
            sa.Column("tool_id", sa.Integer, nullable=True),
            sa.Column("tool_name", sa.String(100), nullable=True),
            sa.Column("rollback_argv", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("reverted_at", sa.DateTime, nullable=True),
            sa.Column("detail", sa.String(500), nullable=True),
        )
        op.create_index("ix_rollback_action_id", "rollback_registrations", ["action_id"])
        op.create_index("ix_rollback_expires_at", "rollback_registrations", ["expires_at"])


def downgrade() -> None:
    if "rollback_registrations" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_rollback_expires_at", table_name="rollback_registrations")
        op.drop_index("ix_rollback_action_id", table_name="rollback_registrations")
        op.drop_table("rollback_registrations")
