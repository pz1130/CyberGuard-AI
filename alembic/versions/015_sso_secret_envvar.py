"""add secret_env_var_id FK to sso_config, references env_vars.id

Revision ID: 015_sso_secret_envvar
Revises: 014_sso
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op

revision = "015_sso_secret_envvar"
down_revision = "014_sso"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sso_config", sa.Column("secret_env_var_id", sa.Integer(), sa.ForeignKey("env_vars.id"), nullable=True))


def downgrade():
    op.drop_column("sso_config", "secret_env_var_id")