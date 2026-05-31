"""ocr: documents.status + ocr_config table

Revision ID: 016_ocr
Revises: 015_sso_secret_envvar
Create Date: 2026-05-31
"""
import sqlalchemy as sa
from alembic import op

revision = "016_ocr"
down_revision = "015_sso_secret_envvar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
    )
    op.add_column(
        "documents",
        sa.Column("status_detail", sa.Text(), nullable=True),
    )

    op.create_table(
        "ocr_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("engine", sa.String(length=20), nullable=False, server_default="tesseract"),
        sa.Column("vision_provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=True),
        sa.Column("vision_model", sa.String(length=255), nullable=True),
        sa.Column("languages", sa.String(length=64), nullable=False, server_default="chi_sim+eng"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ocr_config")
    op.drop_column("documents", "status_detail")
    op.drop_column("documents", "status")
