"""add missing master agent behavior columns (prompts, rounds, threshold)

The MasterAgentConfig model and creation code reference intent_parser_prompt,
summarizer_prompt, max_rounds and auto_approve_threshold, but the original
table migration (de050ef) only created the llm/compression subset. This adds
the behavior columns so that _load_or_create succeeds and Settings can persist them.

Idempotent.

Revision ID: 022_master_prompts
Revises: 021_branding_master
"""

import sqlalchemy as sa
from alembic import op

revision = "022_master_prompts"
down_revision = "021_branding_master"
branch_labels = None
depends_on = None


_BEHAVIOR_COLUMNS = {
    "intent_parser_prompt": sa.Column("intent_parser_prompt", sa.Text(), nullable=True),
    "summarizer_prompt": sa.Column("summarizer_prompt", sa.Text(), nullable=True),
    "max_rounds": sa.Column("max_rounds", sa.Integer(), nullable=True),
    "auto_approve_threshold": sa.Column("auto_approve_threshold", sa.Integer(), nullable=True),
}


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    existing = _existing_columns("master_agent_config")
    for name, column in _BEHAVIOR_COLUMNS.items():
        if name not in existing:
            op.add_column("master_agent_config", column)


def downgrade() -> None:
    existing = _existing_columns("master_agent_config")
    for name in reversed(list(_BEHAVIOR_COLUMNS.keys())):
        if name in existing:
            op.drop_column("master_agent_config", name)
