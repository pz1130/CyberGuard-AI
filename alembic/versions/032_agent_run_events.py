"""agent_run_events: append-only, hash-chained agent run log

Conversation state lived only in conversations.messages_json, rewritten whole on
every append. With multiple API workers that loses concurrent writes, a crash
loses the entire turn, and there is no record of how far a run got — so a run
that dispatched a scan and then died left nothing to recover from.

This table is append-only and chained per run, so it doubles as the evidence
trail for what an agent actually did.

Revision ID: 032_agent_run_events
Revises: 031_agent_governed_flag
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "032_agent_run_events"
down_revision = "031_agent_governed_flag"
branch_labels = None
depends_on = None

_TABLE = "agent_run_events"


def _has_table() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        # Per-run monotonic position. Unique with run_id so a concurrent writer
        # collides instead of silently interleaving.
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # "never" | "safe" | NULL — whether this action may be re-executed after
        # a crash. A read is safe to repeat; a scan or a firewall change is not.
        sa.Column("replay", sa.String(10), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
    )
    op.create_index("ix_agent_run_events_run_id", _TABLE, ["run_id"])
    op.create_index("ix_agent_run_events_agent_created", _TABLE,
                    ["agent_id", "created_at"])
    op.create_index("ix_agent_run_events_type", _TABLE, ["event_type"])


def downgrade() -> None:
    if _has_table():
        op.drop_table(_TABLE)
