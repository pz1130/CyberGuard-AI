"""approval_requests: add required_approver_role + label (A3 routing)

Revision ID: 027_approval_approver_role
Revises: 026_agent_governance
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "027_approval_approver_role"
down_revision = "026_agent_governance"
branch_labels = None
depends_on = None

_COLUMNS = {
    "required_approver_role": sa.Column("required_approver_role", sa.String(20), nullable=True),
    "required_approver_label": sa.Column("required_approver_label", sa.String(100), nullable=True),
}


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("approval_requests")}


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("approval_requests", column)


def downgrade() -> None:
    existing = _existing()
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("approval_requests", name)
