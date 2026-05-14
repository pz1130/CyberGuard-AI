"""Pydantic schemas for governance / GRC endpoints."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Framework + Requirement (catalog)
# ---------------------------------------------------------------------------

class RequirementRead(BaseModel):
    id: int
    framework_id: int
    parent_id: int | None = None
    urn: str
    ref_id: str
    name: str
    description: str | None = None
    depth: int
    order_index: int
    is_assessable: bool
    typical_evidence: list[str] | None = None

    class Config:
        from_attributes = True


class FrameworkRead(BaseModel):
    id: int
    urn: str
    name: str
    version: str | None = None
    description: str | None = None
    locale: str
    ref_url: str | None = None
    is_active: bool
    requirement_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FrameworkWithRequirements(FrameworkRead):
    requirements: list[RequirementRead] = []


class FrameworkImportRequirement(BaseModel):
    ref_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    parent_ref_id: str | None = None
    is_assessable: bool = True
    typical_evidence: list[str] | None = None


class FrameworkImport(BaseModel):
    urn: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    version: str | None = None
    description: str | None = None
    locale: str = "en"
    ref_url: str | None = None
    requirements: list[FrameworkImportRequirement] = Field(default_factory=list)
    replace_existing: bool = False


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

AssessmentStatus = Literal["planning", "in_progress", "completed", "archived"]
RequirementStatus = Literal[
    "not_assessed", "compliant", "partially_compliant", "non_compliant", "not_applicable"
]
EvidenceKind = Literal["file", "url", "text"]


class EvidenceRead(BaseModel):
    id: int
    requirement_assessment_id: int
    name: str
    description: str | None = None
    kind: EvidenceKind
    file_path: str | None = None
    url: str | None = None
    body: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class EvidenceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    kind: EvidenceKind = "text"
    url: str | None = None
    body: str | None = None
    mime_type: str | None = None


class RequirementAssessmentRead(BaseModel):
    id: int
    assessment_id: int
    requirement_id: int
    status: RequirementStatus
    score: int | None = None
    observation: str | None = None
    ai_recommendation: str | None = None
    ai_assessed_at: datetime | None = None
    updated_at: datetime
    evidences: list[EvidenceRead] = []
    requirement: RequirementRead | None = None

    class Config:
        from_attributes = True


class RequirementAssessmentUpdate(BaseModel):
    status: RequirementStatus | None = None
    score: int | None = Field(None, ge=0, le=100)
    observation: str | None = None


class ComplianceAssessmentRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    framework_id: int
    framework_name: str | None = None
    scope: str | None = None
    status: AssessmentStatus
    start_date: datetime | None = None
    due_date: datetime | None = None
    owner_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
    progress: dict | None = None  # {total, assessed, compliant, ...}

    class Config:
        from_attributes = True


class ComplianceAssessmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    framework_id: int
    scope: str | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None


class ComplianceAssessmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    scope: str | None = None
    status: AssessmentStatus | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------

class AISuggestEvidenceResponse(BaseModel):
    requirement_id: int
    suggestions: list[str]


class AIAssessRequestRequest(BaseModel):
    extra_context: str | None = None
    apply: bool = False  # if True, also update the row with the AI verdict


class AIAssessResponse(BaseModel):
    requirement_id: int
    status: RequirementStatus
    score: int | None = None
    observation: str
    applied: bool


class AIReportResponse(BaseModel):
    assessment_id: int
    markdown: str
