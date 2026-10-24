from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

FindingStatus = Literal["pending", "confirmed", "in_progress", "ready_for_retest", "resolved", "rejected"]
Severity = Literal["info", "low", "medium", "high", "critical"]


class FindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=1000)
    severity: Severity
    description: str = Field(min_length=1, max_length=20000)
    remediation: str = Field(min_length=1, max_length=20000)
    evidence: str = Field(min_length=1, max_length=65536)

    @field_validator("title", "target", "description", "remediation", "evidence")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value  # Evidence must remain byte-for-byte intact.


class FindingChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm", "reject", "assign", "ready", "resolve", "reopen", "evidence"]
    version: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=10000)
    evidence: str = Field(default="", max_length=65536)
    assignee_id: int | None = Field(default=None, gt=0)

    @field_validator("note")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("A review note is required")
        return value
