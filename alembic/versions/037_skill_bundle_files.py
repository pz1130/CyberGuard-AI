"""Store bundled resource files for skills imported from a zip bundle.

Revision ID: 037_skill_bundle_files
Revises: 036_knowledge_provider_binding
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "037_skill_bundle_files"
down_revision: Union[str, None] = "036_knowledge_provider_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_blob", sa.LargeBinary(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mime", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_path"),
    )
    op.create_index("ix_skill_files_id", "skill_files", ["id"])
    op.create_index("ix_skill_files_skill_id", "skill_files", ["skill_id"])


def downgrade() -> None:
    op.drop_index("ix_skill_files_skill_id", table_name="skill_files")
    op.drop_index("ix_skill_files_id", table_name="skill_files")
    op.drop_table("skill_files")
