"""Drop group_chat_messages — the human-to-human WebSocket room chat is removed.

Revision ID: 005_drop_room_chat
Revises: 004_multi_dim_embeddings
Create Date: 2026-05-12 14:00:00.000000

The ROOM CHAT feature (WebSocket-based, operator ↔ operator, no AI) was removed
because single-operator deployments had no use for it. Multi-agent group chat
(REST sessions persisted in Redis) is unaffected — it never used this table.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "005_drop_room_chat"
down_revision: Union[str, None] = "004_multi_dim_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_group_chat_messages_room_created")
    op.execute("DROP INDEX IF EXISTS ix_group_chat_messages_room_id")
    op.execute("DROP INDEX IF EXISTS ix_group_chat_messages_created_at")
    op.execute("DROP INDEX IF EXISTS ix_group_chat_messages_id")
    op.execute("DROP TABLE IF EXISTS group_chat_messages")


def downgrade() -> None:
    # Recreate the legacy schema (matches the deleted app/models/groupchat.py).
    op.execute("""
        CREATE TABLE group_chat_messages (
            id            SERIAL PRIMARY KEY,
            room_id       VARCHAR(64) NOT NULL,
            user_id       INTEGER,
            username      VARCHAR(100) NOT NULL,
            content       TEXT NOT NULL,
            metadata_json VARCHAR(500),
            created_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_group_chat_messages_id ON group_chat_messages (id)")
    op.execute("CREATE INDEX ix_group_chat_messages_room_id ON group_chat_messages (room_id)")
    op.execute("CREATE INDEX ix_group_chat_messages_created_at ON group_chat_messages (created_at)")
    op.execute("CREATE INDEX ix_group_chat_messages_room_created ON group_chat_messages (room_id, created_at)")
