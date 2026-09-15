"""Per-agent mode for model-authored code execution.

Revision ID: 039_agent_code_execution_mode
Revises: 038_skill_script_tools
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "039_agent_code_execution_mode"
down_revision: Union[str, None] = "038_skill_script_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("code_execution_mode", sa.String(length=20),
                  nullable=False, server_default="approval"),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "code_execution_mode")
