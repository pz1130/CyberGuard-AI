"""add backup_records table

Revision ID: 020b_backup_records
Revises: 020_approval_requests
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020b_backup_records'
down_revision: Union[str, None] = '020_approval_requests'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'backup_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('format', sa.String(length=50), nullable=False),
        sa.Column('local_path', sa.String(length=500), nullable=True),
        sa.Column('remote_url', sa.String(length=1000), nullable=True),
        sa.Column('s3_bucket', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retention_days', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('backup_records')
