"""Governance: frameworks, requirements, assessments, evidence.

Revision ID: 008_governance
Revises: 007_prompt_templates
Create Date: 2026-05-14 01:00:00.000000

Adds a minimal GRC layer inspired by CISO Assistant:
  gov_frameworks → gov_requirements (tree)
  gov_assessments → gov_requirement_assessments → gov_evidences
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_governance"
down_revision: Union[str, None] = "007_prompt_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ASSESSMENT_STATUSES = "('planning','in_progress','completed','archived')"
REQ_STATUSES = "('not_assessed','compliant','partially_compliant','non_compliant','not_applicable')"
EVIDENCE_KINDS = "('file','url','text')"


def upgrade() -> None:
    # gov_frameworks ---------------------------------------------------------
    op.create_table(
        "gov_frameworks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("urn", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("locale", sa.String(16), nullable=False, server_default="en"),
        sa.Column("ref_url", sa.String(1024), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("urn", name="uq_gov_frameworks_urn"),
    )
    op.create_index("ix_gov_frameworks_id", "gov_frameworks", ["id"])
    op.create_index("ix_gov_frameworks_urn", "gov_frameworks", ["urn"])

    # gov_requirements -------------------------------------------------------
    op.create_table(
        "gov_requirements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("urn", sa.String(255), nullable=False),
        sa.Column("ref_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_assessable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["framework_id"], ["gov_frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["gov_requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "ref_id", name="uq_requirement_framework_refid"),
    )
    op.create_index("ix_gov_requirements_id", "gov_requirements", ["id"])
    op.create_index("ix_gov_requirements_urn", "gov_requirements", ["urn"])
    op.create_index("ix_gov_requirements_framework_id", "gov_requirements", ["framework_id"])
    op.create_index("ix_gov_requirements_parent_id", "gov_requirements", ["parent_id"])
    op.create_index("ix_gov_requirements_framework_parent", "gov_requirements", ["framework_id", "parent_id"])

    # gov_assessments --------------------------------------------------------
    op.create_table(
        "gov_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="planning"),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["framework_id"], ["gov_frameworks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"status IN {ASSESSMENT_STATUSES}", name="ck_gov_assessment_status"),
    )
    op.create_index("ix_gov_assessments_id", "gov_assessments", ["id"])
    op.create_index("ix_gov_assessments_framework_id", "gov_assessments", ["framework_id"])

    # gov_requirement_assessments -------------------------------------------
    op.create_table(
        "gov_requirement_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_assessed"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("ai_recommendation", sa.Text(), nullable=True),
        sa.Column("ai_assessed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["gov_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["gov_requirements.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "requirement_id", name="uq_req_assessment_unique"),
        sa.CheckConstraint(f"status IN {REQ_STATUSES}", name="ck_gov_req_assessment_status"),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_gov_req_assessment_score"),
    )
    op.create_index("ix_gov_req_assessments_id", "gov_requirement_assessments", ["id"])
    op.create_index("ix_gov_req_assessments_assessment_id", "gov_requirement_assessments", ["assessment_id"])
    op.create_index("ix_gov_req_assessments_requirement_id", "gov_requirement_assessments", ["requirement_id"])

    # gov_evidences ----------------------------------------------------------
    op.create_table(
        "gov_evidences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requirement_assessment_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="text"),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["requirement_assessment_id"], ["gov_requirement_assessments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"kind IN {EVIDENCE_KINDS}", name="ck_gov_evidence_kind"),
    )
    op.create_index("ix_gov_evidences_id", "gov_evidences", ["id"])
    op.create_index("ix_gov_evidences_req_assessment_id", "gov_evidences", ["requirement_assessment_id"])


def downgrade() -> None:
    op.drop_table("gov_evidences")
    op.drop_table("gov_requirement_assessments")
    op.drop_table("gov_assessments")
    op.drop_table("gov_requirements")
    op.drop_table("gov_frameworks")
