"""Prompt templates table.

Revision ID: 007_prompt_templates
Revises: 006_webhooks
Create Date: 2026-05-14 00:00:00.000000

User-defined reusable system prompts that can be selected from the
Chat "CUSTOM SYSTEM PROMPT" panel.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_prompt_templates"
down_revision: Union[str, None] = "006_webhooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="general"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_prompt_templates_name"),
        sa.CheckConstraint(
            "category IN ('system', 'intent_parser', 'summarizer', 'general')",
            name="ck_prompt_templates_category",
        ),
    )
    op.create_index("ix_prompt_templates_id", "prompt_templates", ["id"])
    op.create_index("ix_prompt_templates_name", "prompt_templates", ["name"])


def downgrade() -> None:
    op.drop_index("ix_prompt_templates_name", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")
