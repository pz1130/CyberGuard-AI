"""Bind each knowledge base to its embedding provider.

Revision ID: 036_knowledge_provider_binding
Revises: 035_audit_chain_v2
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "036_knowledge_provider_binding"
down_revision: Union[str, None] = "035_audit_chain_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_bases", sa.Column("provider_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_knowledge_bases_provider_id_providers",
        "knowledge_bases", "providers", ["provider_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_knowledge_bases_provider_id_providers",
        "knowledge_bases", type_="foreignkey",
    )
    op.drop_column("knowledge_bases", "provider_id")
