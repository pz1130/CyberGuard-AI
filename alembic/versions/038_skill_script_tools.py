"""Promote reviewed skill bundle scripts into tools.

Revision ID: 038_skill_script_tools
Revises: 037_skill_bundle_files
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "038_skill_script_tools"
down_revision: Union[str, None] = "037_skill_bundle_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("source_skill_id", sa.Integer(), nullable=True))
    op.add_column("tools", sa.Column("source_script_path", sa.String(length=500), nullable=True))
    op.add_column("tools", sa.Column("source_bundle_digest", sa.String(length=64), nullable=True))
    op.add_column("tools", sa.Column("script_network", sa.String(length=20), nullable=True))
    op.add_column("tools", sa.Column("script_network_allowlist", sa.JSON(), nullable=True))
    op.create_index("ix_tools_source_skill_id", "tools", ["source_skill_id"])
    op.create_foreign_key(
        "fk_tools_source_skill_id_skills", "tools", "skills",
        ["source_skill_id"], ["id"], ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_tools_skill_script_shape", "tools",
        "source_skill_id IS NULL OR ("
        "source_script_path IS NOT NULL AND source_bundle_digest IS NOT NULL "
        "AND script_network IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tools_skill_script_shape", "tools", type_="check")
    op.drop_constraint("fk_tools_source_skill_id_skills", "tools", type_="foreignkey")
    op.drop_index("ix_tools_source_skill_id", table_name="tools")
    for col in ("script_network_allowlist", "script_network", "source_bundle_digest",
                "source_script_path", "source_skill_id"):
        op.drop_column("tools", col)
