"""Governance / Compliance models.

Inspired by intuitem/ciso-assistant-community (AGPL). We re-create a
minimal set of GRC primitives that fits CyberGuard's agent-driven
operations rather than copying their code.

Hierarchy:

    Framework  (e.g. ISO 27001:2022 Annex A)
      └─ Requirement (tree, e.g. A.5 → A.5.1 → A.5.1.1)

    ComplianceAssessment   (an audit run, scoped to one Framework)
      └─ RequirementAssessment (status + observation per requirement)
            └─ Evidence (file path / URL / text body)
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    CheckConstraint, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


# ---------------------------------------------------------------------------
# Framework + Requirement (the "catalog" side — what to assess against)
# ---------------------------------------------------------------------------

class Framework(Base):
    __tablename__ = "gov_frameworks"

    id = Column(Integer, primary_key=True, index=True)
    urn = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    version = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    locale = Column(String(16), nullable=False, default="en")
    ref_url = Column(String(1024), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    requirements = relationship(
        "Requirement",
        back_populates="framework",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Requirement(Base):
    """A single line item within a framework, possibly nested under a parent."""

    __tablename__ = "gov_requirements"

    id = Column(Integer, primary_key=True, index=True)
    framework_id = Column(Integer, ForeignKey("gov_frameworks.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("gov_requirements.id", ondelete="CASCADE"), nullable=True, index=True)
    urn = Column(String(255), nullable=False, index=True)
    ref_id = Column(String(64), nullable=False)  # e.g. "A.5.1"
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    depth = Column(Integer, nullable=False, default=0)
    order_index = Column(Integer, nullable=False, default=0)
    is_assessable = Column(Boolean, nullable=False, default=True)  # categories may be non-assessable

    framework = relationship("Framework", back_populates="requirements")
    parent = relationship("Requirement", remote_side="Requirement.id", backref="children")

    __table_args__ = (
        UniqueConstraint("framework_id", "ref_id", name="uq_requirement_framework_refid"),
        Index("ix_gov_requirements_framework_parent", "framework_id", "parent_id"),
    )


# ---------------------------------------------------------------------------
# ComplianceAssessment + RequirementAssessment + Evidence (the "audit" side)
# ---------------------------------------------------------------------------

ASSESSMENT_STATUS = ("planning", "in_progress", "completed", "archived")
REQ_STATUS = ("not_assessed", "compliant", "partially_compliant", "non_compliant", "not_applicable")


class ComplianceAssessment(Base):
    __tablename__ = "gov_assessments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    framework_id = Column(Integer, ForeignKey("gov_frameworks.id", ondelete="RESTRICT"), nullable=False, index=True)
    scope = Column(Text, nullable=True)  # free-text scope ("Production AWS account", etc.)
    status = Column(String(32), nullable=False, default="planning")
    start_date = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    owner_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    framework = relationship("Framework")
    requirement_assessments = relationship(
        "RequirementAssessment",
        back_populates="assessment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN {ASSESSMENT_STATUS!r}",
            name="ck_gov_assessment_status",
        ),
    )


class RequirementAssessment(Base):
    __tablename__ = "gov_requirement_assessments"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("gov_assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(Integer, ForeignKey("gov_requirements.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="not_assessed")
    score = Column(Integer, nullable=True)  # 0-100 maturity score, optional
    observation = Column(Text, nullable=True)
    ai_recommendation = Column(Text, nullable=True)  # last AI assessment output
    ai_assessed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = Column(Integer, nullable=True)

    assessment = relationship("ComplianceAssessment", back_populates="requirement_assessments")
    requirement = relationship("Requirement", lazy="joined")
    evidences = relationship(
        "Evidence",
        back_populates="requirement_assessment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("assessment_id", "requirement_id", name="uq_req_assessment_unique"),
        CheckConstraint(
            f"status IN {REQ_STATUS!r}",
            name="ck_gov_req_assessment_status",
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_gov_req_assessment_score"),
    )


class Evidence(Base):
    """File path, URL, or inline text supporting a requirement assessment."""

    __tablename__ = "gov_evidences"

    id = Column(Integer, primary_key=True, index=True)
    requirement_assessment_id = Column(
        Integer,
        ForeignKey("gov_requirement_assessments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # One of: "file" | "url" | "text"
    kind = Column(String(16), nullable=False, default="text")
    file_path = Column(String(1024), nullable=True)
    url = Column(String(1024), nullable=True)
    body = Column(Text, nullable=True)
    mime_type = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    uploaded_by_user_id = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    requirement_assessment = relationship("RequirementAssessment", back_populates="evidences")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('file', 'url', 'text')",
            name="ck_gov_evidence_kind",
        ),
    )
