"""add approval_requests table for human-in-the-loop approvals

Revision ID: 020_approval_requests
Revises: 019_scheduled_tasks
Create Date: 2026-06-05 09:45:53.039374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_approval_requests'
down_revision: Union[str, None] = '019_scheduled_tasks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('approver_id', sa.Integer(), nullable=True),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('agent_name', sa.String(length=100), nullable=True),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('action_description', sa.Text(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True),
        sa.Column('urgency', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('approver_comment', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_approval_requests_created_at'), 'approval_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_approval_requests_id'), 'approval_requests', ['id'], unique=False)
    op.create_index(op.f('ix_approval_requests_request_id'), 'approval_requests', ['request_id'], unique=True)
    op.create_index(op.f('ix_approval_requests_status'), 'approval_requests', ['status'], unique=False)
    op.create_index(op.f('ix_approval_requests_user_id'), 'approval_requests', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_approval_requests_user_id'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_status'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_request_id'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_id'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_created_at'), table_name='approval_requests')
    op.drop_table('approval_requests')
