"""add master_agent_config table

Revision ID: 020d_master_agent_config
Revises: 020c_n8n_connections
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020d_master_agent_config'
down_revision: Union[str, None] = '020c_n8n_connections'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'master_agent_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('llm_provider_id', sa.Integer(), nullable=True),
        sa.Column('llm_model', sa.String(length=100), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('context_compression_enabled', sa.Boolean(), nullable=False),
        sa.Column('compression_model', sa.String(length=100), nullable=True),
        sa.Column('compression_max_tokens', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_master_agent_config_id'), 'master_agent_config', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_master_agent_config_id'), table_name='master_agent_config')
    op.drop_table('master_agent_config')
