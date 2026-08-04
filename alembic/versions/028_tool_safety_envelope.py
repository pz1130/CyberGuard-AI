"""tools: safety-envelope command templates (validation/verification/rollback)

Revision ID: 028_tool_safety_envelope
Revises: 027_approval_approver_role
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "028_tool_safety_envelope"
down_revision = "027_approval_approver_role"
branch_labels = None
depends_on = None

_COLS = ("validation_command_template", "verification_command_template", "rollback_command_template")


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tools")}


def upgrade() -> None:
    existing = _existing()
    for c in _COLS:
        if c not in existing:
            op.add_column("tools", sa.Column(c, sa.Text(), nullable=True))


def downgrade() -> None:
    existing = _existing()
    for c in reversed(_COLS):
        if c in existing:
            op.drop_column("tools", c)
