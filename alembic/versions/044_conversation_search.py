"""Indexes for user-scoped chat message search.

Round 1 planned a tsvector column. PostgreSQL tokenises a whole Chinese
sentence as one lexeme and zhparser is not in the image, so full-text search
cannot match a keyword inside Chinese content. pg_trgm can.

The owner index is partial. A tombstoned conversation and an internal agent's
memory slice are both rows a person owns and neither belongs in their search
results, so they are absent from the index rather than filtered out by every
query that remembers to.

Revision ID: 044_conversation_search  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 043_drop_dead_security_toggles
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "044_conversation_search"
down_revision: Union[str, None] = "043_drop_dead_security_toggles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # conversations.user_id had no index at all, so this also makes the
    # existing list_conversations cheaper.
    op.create_index(
        "ix_conv_user_live", "conversations", ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL AND agent_id IS NULL"),
    )
    op.create_index(
        "ix_conv_messages_content_trgm", "conversation_messages", ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_conv_messages_content_trgm", table_name="conversation_messages")
    op.drop_index("ix_conv_user_live", table_name="conversations")
    # The extension is left installed: another table may have come to depend on
    # it, and dropping it would take those indexes with it.
