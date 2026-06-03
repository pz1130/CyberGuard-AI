"""audit_logs: add ip_address/user_agent/request_path/metadata_json columns

The AuditLog model (app/models/audit.py) declares ip_address, user_agent,
request_path and metadata_json, but 001_initial created audit_logs without them.
On DBs built from the migration chain the table was missing these columns, so the
fire-and-forget log_audit() writer raised
`UndefinedColumnError: column "ip_address" of relation "audit_logs" does not exist`
on every audited request. This brings the table in line with the model.

Idempotent: only adds columns that are absent, so it is safe regardless of whether
001_initial is later amended to include them.

Revision ID: 018_audit_logs_columns
Revises: 017_agent_episodes
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op

revision = "018_audit_logs_columns"
down_revision = "017_agent_episodes"
branch_labels = None
depends_on = None


_COLUMNS = {
    "ip_address": sa.Column("ip_address", sa.String(length=45), nullable=True),
    "user_agent": sa.Column("user_agent", sa.String(length=500), nullable=True),
    "request_path": sa.Column("request_path", sa.String(length=500), nullable=True),
    "metadata_json": sa.Column("metadata_json", sa.JSON(), nullable=True),
}


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns("audit_logs")}


def upgrade() -> None:
    existing = _existing_columns()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("audit_logs", column)


def downgrade() -> None:
    existing = _existing_columns()
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("audit_logs", name)
