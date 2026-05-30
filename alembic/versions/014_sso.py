"""add Azure AD SSO: users columns + sso_config + sso_role_mapping

Revision ID: 014_sso
Revises: 013_security_settings
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op

revision = "014_sso"
down_revision = "013_security_settings"
branch_labels = None
depends_on = None


def upgrade():
    # users: SSO accounts have no local password and carry an external identity.
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(50), nullable=False, server_default="local"),
    )
    op.add_column("users", sa.Column("external_id", sa.String(255), nullable=True))
    op.create_index("ix_users_external_id", "users", ["external_id"])

    op.create_table(
        "sso_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("client_id", sa.String(255), nullable=True),
        sa.Column("redirect_uri", sa.String(512), nullable=True),
        sa.Column("default_role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("allow_jit", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "INSERT INTO sso_config (id, enabled, default_role, allow_jit) "
        "VALUES (1, false, 'viewer', true)"
    )

    op.create_table(
        "sso_role_mapping",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("azure_key", sa.String(255), nullable=False),
        sa.Column("app_role", sa.String(50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sso_role_mapping_azure_key", "sso_role_mapping", ["azure_key"], unique=True)


def downgrade():
    op.drop_index("ix_sso_role_mapping_azure_key", table_name="sso_role_mapping")
    op.drop_table("sso_role_mapping")
    op.drop_table("sso_config")
    op.drop_index("ix_users_external_id", table_name="users")
    op.drop_column("users", "external_id")
    op.drop_column("users", "auth_provider")
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
