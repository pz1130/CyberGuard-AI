"""tool pool executable columns

Revision ID: 011_tool_executable
Revises: 010_agent_kind_and_internal
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "011_tool_executable"
down_revision = "010_agent_kind_and_internal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("command_template", sa.Text(), nullable=True))
    op.add_column("tools", sa.Column("input_schema_json", sa.Text(), nullable=True))
    op.add_column("tools", sa.Column("timeout_seconds", sa.Integer(),
                                     nullable=False, server_default="60"))
    op.add_column("tools", sa.Column("required_permission", sa.String(100), nullable=True))
    op.create_index("ix_tools_required_permission", "tools", ["required_permission"])
    op.alter_column("tools", "md_content", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("tools", "md_content", existing_type=sa.Text(), nullable=False)
    op.drop_index("ix_tools_required_permission", table_name="tools")
    op.drop_column("tools", "required_permission")
    op.drop_column("tools", "timeout_seconds")
    op.drop_column("tools", "input_schema_json")
    op.drop_column("tools", "command_template")
