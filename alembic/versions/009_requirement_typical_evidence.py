"""Add typical_evidence JSON column to gov_requirements.

Revision ID: 009_req_typical_evidence
Revises: 008_governance
Create Date: 2026-05-14 02:00:00.000000

Stores a canonical evidence checklist per control so the UI can show
official, framework-version-stable suggestions without re-rolling an LLM.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_req_typical_evidence"
down_revision: Union[str, None] = "008_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gov_requirements",
        sa.Column("typical_evidence", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gov_requirements", "typical_evidence")
