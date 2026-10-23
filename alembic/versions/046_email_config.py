"""Persist notification mailbox settings."""
import sqlalchemy as sa
from alembic import op

revision = "046_email_config"
down_revision = "045_conversation_retention"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=True),
        sa.Column("oauth_client_secret_encrypted", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table("email_config")
