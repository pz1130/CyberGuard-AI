"""tools/mcp_tools: add action_category + risk_tier

Revision ID: 024_action_taxonomy
Revises: 023_audit_chain
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "024_action_taxonomy"
down_revision = "023_audit_chain"
branch_labels = None
depends_on = None

_TABLES = ("tools", "mcp_tools")
_COLS = ("action_category", "risk_tier")


def _existing(table) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for t in _TABLES:
        existing = _existing(t)
        for c in _COLS:
            if c not in existing:
                op.add_column(t, sa.Column(c, sa.String(length=20), nullable=True))


def downgrade() -> None:
    for t in _TABLES:
        existing = _existing(t)
        for c in reversed(_COLS):
            if c in existing:
                op.drop_column(t, c)
