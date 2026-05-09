"""OpenClaw Gateway: add api_key_hash, openclaw_last_seen to agent_configs, create gateway_messages table

Revision ID: 002_openclaw_gateway
Revises: 001_initial
Create Date: 2026-05-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_openclaw_gateway"
down_revision: Union[str, None] = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add OpenClaw gateway columns to agent_configs
    op.add_column("agent_configs", sa.Column("api_key_hash", sa.String(128), nullable=True))
    op.add_column("agent_configs", sa.Column("openclaw_last_seen", sa.DateTime(), nullable=True))

    # Create gateway_messages table
    op.create_table(
        "gateway_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=True),
        sa.Column("execution_id", sa.String(36), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gateway_messages_id", "gateway_messages", ["id"])
    op.create_index("ix_gateway_messages_agent_id", "gateway_messages", ["agent_id"])
    op.create_index("ix_gateway_messages_status", "gateway_messages", ["status"])
    op.create_index("ix_gateway_messages_execution_id", "gateway_messages", ["execution_id"])


def downgrade() -> None:
    op.drop_table("gateway_messages")
    op.drop_column("agent_configs", "openclaw_last_seen")
    op.drop_column("agent_configs", "api_key_hash")
