"""Record a conversation's WORM export, and that it was purged.

Retention disposes of messages; it must not dispose of the account of them.
The conversations row survives a purge carrying purged_at and export_key, so
the chain anchors written in Round 1 still name something that resolves.

Revision ID: 045_conversation_retention  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 044_conversation_search
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "045_conversation_retention"
down_revision: Union[str, None] = "044_conversation_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_exports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=300), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("head_seq", sa.Integer(), nullable=False),
        sa.Column("head_hash", sa.String(length=64), nullable=False),
        sa.Column("retain_until", sa.DateTime(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conv_exports_conv", "conversation_exports",
                    ["conversation_id", "head_seq"])

    op.add_column("conversations", sa.Column("purged_at", sa.DateTime(), nullable=True))
    op.add_column("conversations",
                  sa.Column("export_key", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "export_key")
    op.drop_column("conversations", "purged_at")
    op.drop_index("ix_conv_exports_conv", table_name="conversation_exports")
    op.drop_table("conversation_exports")
