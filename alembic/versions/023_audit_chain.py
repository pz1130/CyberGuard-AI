"""audit_logs: add governance fields + hash chain (prev_hash/entry_hash)

Revision ID: 023_audit_chain
Revises: 022_master_prompts
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "023_audit_chain"
down_revision = "022_master_prompts"
branch_labels = None
depends_on = None

_COLUMNS = {
    "agent_name": sa.Column("agent_name", sa.String(length=100), nullable=True),
    "action_category": sa.Column("action_category", sa.String(length=20), nullable=True),
    "confidence": sa.Column("confidence", sa.String(length=10), nullable=True),
    "human_reviewer": sa.Column("human_reviewer", sa.String(length=255), nullable=True),
    "rollback_possible": sa.Column("rollback_possible", sa.Boolean(), nullable=True),
    "risk_tier": sa.Column("risk_tier", sa.String(length=20), nullable=True),
    "prev_hash": sa.Column("prev_hash", sa.String(length=64), nullable=True),
    "entry_hash": sa.Column("entry_hash", sa.String(length=64), nullable=True),
}


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("audit_logs")}


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("audit_logs", column)
    if "entry_hash" not in existing:
        op.create_index("ix_audit_logs_entry_hash", "audit_logs", ["entry_hash"])


def downgrade() -> None:
    existing = _existing()
    if "entry_hash" in existing:
        op.drop_index("ix_audit_logs_entry_hash", table_name="audit_logs")
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("audit_logs", name)
