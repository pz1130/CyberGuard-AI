"""Webhooks table (bi-directional).

Revision ID: 006_webhooks
Revises: 005_drop_room_chat
Create Date: 2026-05-13 00:00:00.000000

direction='incoming' rows: external services POST to /api/v1/webhooks/incoming/<token>
direction='outgoing' rows: CyberGuard POSTs to outgoing_url on subscribed events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_webhooks"
down_revision: Union[str, None] = "005_drop_room_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Incoming
        sa.Column("incoming_token_hash", sa.String(128), nullable=True),
        # Outgoing
        sa.Column("outgoing_url", sa.String(1024), nullable=True),
        sa.Column("outgoing_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("outgoing_events", sa.JSON(), nullable=True),
        # Stats
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_webhooks_name"),
        sa.CheckConstraint("direction IN ('incoming', 'outgoing')", name="ck_webhooks_direction"),
        sa.CheckConstraint(
            "(direction = 'outgoing' AND outgoing_url IS NOT NULL) "
            "OR (direction = 'incoming' AND incoming_token_hash IS NOT NULL)",
            name="ck_webhooks_direction_fields",
        ),
    )
    op.create_index("ix_webhooks_id", "webhooks", ["id"])
    op.create_index("ix_webhooks_name", "webhooks", ["name"])
    op.create_index("ix_webhooks_incoming_token_hash", "webhooks", ["incoming_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_webhooks_incoming_token_hash", table_name="webhooks")
    op.drop_index("ix_webhooks_name", table_name="webhooks")
    op.drop_index("ix_webhooks_id", table_name="webhooks")
    op.drop_table("webhooks")
