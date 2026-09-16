"""Chat messages become append-only, hash-chained rows.

History lived in conversations.messages_json, a single JSON array: every
append rewrote the whole blob, and PUT /conversations/{id} could replace the
transcript in one request. Neither is compatible with the transcript being
evidence of what the assistant said.

Existing blobs are backfilled and every backfilled row is flagged, because
hashes computed here prove only that nothing changed after this migration.
messages_json is left in place — a rollback would otherwise lose history that
exists nowhere else at that moment — and a later migration drops it.

Revision ID: 041_conversation_messages  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 040_conv_title_no_default
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "041_conversation_messages"
down_revision: Union[str, None] = "040_conv_title_no_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BATCH = 200


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("turn_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("backfilled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_conv_messages_seq"),
    )
    op.create_index("ix_conv_messages_conv_seq", "conversation_messages",
                    ["conversation_id", "seq"])

    op.add_column("conversations", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("conversations", sa.Column(
        "last_anchored_seq", sa.Integer(), nullable=False, server_default="-1"))

    _backfill()


def _backfill() -> None:
    # Imported here rather than at module scope so that a downgrade, or an
    # `alembic history`, does not need the app package importable.
    from app.services.conversation_backfill import rows_for_conversation

    conn = op.get_bind()
    insert = sa.text(
        "INSERT INTO conversation_messages "
        "(conversation_id, seq, role, content, run_id, turn_id, created_at,"
        " backfilled, prev_hash, entry_hash) "
        "VALUES (:conversation_id, :seq, :role, :content, :run_id, :turn_id,"
        " :created_at, :backfilled, :prev_hash, :entry_hash)"
    )

    last_id = 0
    while True:
        batch = conn.execute(sa.text(
            "SELECT id, messages_json, created_at FROM conversations "
            "WHERE id > :last_id AND messages_json IS NOT NULL "
            "AND messages_json NOT IN ('', '[]') "
            "ORDER BY id LIMIT :limit"
        ), {"last_id": last_id, "limit": _BATCH}).fetchall()
        if not batch:
            return
        for conv_id, messages_json, conv_created_at in batch:
            for row in rows_for_conversation(conv_id, messages_json, conv_created_at):
                conn.execute(insert, row)
            last_id = conv_id


def downgrade() -> None:
    op.drop_column("conversations", "last_anchored_seq")
    op.drop_column("conversations", "deleted_at")
    op.drop_index("ix_conv_messages_conv_seq", table_name="conversation_messages")
    op.drop_table("conversation_messages")
