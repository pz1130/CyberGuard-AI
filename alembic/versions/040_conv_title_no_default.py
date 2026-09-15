"""Drop the Chinese server-side default on conversations.title.

The column carried DEFAULT '新对话' from 010, so a row inserted without a title
got a Chinese placeholder from the database itself — visible to every reader
whatever language their UI is set to. An untitled conversation is now NULL and
the client renders its own translated placeholder.

Revision ID: 040_conv_title_no_default  (kept short: alembic_version.version_num is varchar(32))
Revises: 039_agent_code_execution_mode
Create Date: 2026-09-15
"""
from typing import Sequence, Union

from alembic import op


revision: str = "040_conv_title_no_default"
down_revision: Union[str, None] = "039_agent_code_execution_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ALTER COLUMN title DROP DEFAULT")


def downgrade() -> None:
    op.execute("ALTER TABLE conversations ALTER COLUMN title SET DEFAULT '新对话'")
