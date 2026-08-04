"""audit_worm_exports marker table

Revision ID: 030_audit_worm_exports
Revises: 029_rollback_registry
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "030_audit_worm_exports"
down_revision = "029_rollback_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "audit_worm_exports" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "audit_worm_exports",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("last_audit_id", sa.Integer, nullable=False),
            sa.Column("object_key", sa.String(300), nullable=False),
            sa.Column("rows", sa.Integer, nullable=False),
            sa.Column("retain_until", sa.DateTime, nullable=True),
            sa.Column("exported_at", sa.DateTime, nullable=False),
        )


def downgrade() -> None:
    if "audit_worm_exports" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("audit_worm_exports")
