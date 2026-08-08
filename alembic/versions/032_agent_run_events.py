"""agent_run_events: durable sink for the agent audit event stream

``agent_core.events.AuditBus`` emits four-layer events (agent / turn / message /
tool_execution, each start → update → end) from the tool pipeline and the run
loop, but the process-default bus ships with zero subscribers — "emit is a
no-op". So the stream that is supposed to be the evidence trail went nowhere,
and a run that dispatched a scan and then died left nothing to recover from.

This table is the sink: append-only and hash-chained per run, so a missing or
altered row is detectable. ``tool_execution/start`` is emitted before the tool
runs, which is what makes crash recovery possible — the interesting case is the
process dying *during* an action.

Revision ID: 032_agent_run_events
Revises: 031_agent_governed_flag
Create Date: 2026-08-08
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
        # AuditLayer / AuditPhase, kept as plain strings so a new layer does
        # not require a migration.
        sa.Column("layer", sa.String(32), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("turn_id", sa.String(64), nullable=True),
        sa.Column("tool_call_id", sa.String(64), nullable=True),
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
    op.create_index("ix_agent_run_events_layer_phase", _TABLE, ["layer", "phase"])


def downgrade() -> None:
    if _has_table():
        op.drop_table(_TABLE)
