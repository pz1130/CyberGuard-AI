"""add branding columns to master_agent_config

Adds branding_logo (TEXT, for base64 data URL) and branding_company_name (VARCHAR)
to support the 品牌/Branding feature in Settings.

Idempotent using inspector (safe if table/cols already present).

Revision ID: 021_add_branding_columns_to_master_agent_config
Revises: 020d_master_agent_config
"""

import sqlalchemy as sa
from alembic import op

revision = "021_branding_master"
down_revision = "020d_master_agent_config"
branch_labels = None
depends_on = None


_BRANDING_COLUMNS = {
    "branding_logo": sa.Column("branding_logo", sa.Text(), nullable=True),
    "branding_company_name": sa.Column("branding_company_name", sa.String(length=100), nullable=True),
}


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    existing = _existing_columns("master_agent_config")
    for name, column in _BRANDING_COLUMNS.items():
        if name not in existing:
            op.add_column("master_agent_config", column)


def downgrade() -> None:
    existing = _existing_columns("master_agent_config")
    for name in reversed(list(_BRANDING_COLUMNS.keys())):
        if name in existing:
            op.drop_column("master_agent_config", name)
