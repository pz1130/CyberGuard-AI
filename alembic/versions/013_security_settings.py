"""add security_settings table

Revision ID: 013_security_settings
Revises: 012_pool_assignment_tags
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op

revision = "013_security_settings"
down_revision = "012_pool_assignment_tags"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encryption_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("rbac_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("audit_logging", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_login_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("api_key_rotation_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "INSERT INTO security_settings "
        "(id, encryption_enabled, rbac_enabled, audit_logging, "
        "max_login_attempts, session_timeout_minutes, api_key_rotation_days) "
        "VALUES (1, true, true, true, 5, 30, 90)"
    )


def downgrade():
    op.drop_table("security_settings")
