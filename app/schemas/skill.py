"""Pydantic schemas for skill and tool management."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class SkillBase(BaseModel):
    """Base skill schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    permission_level: str = "medium"
    requires_approval: bool = False
    is_active: bool = True
    tags: Optional[List[str]] = None


class SkillCreate(SkillBase):
    """Skill creation schema."""
    md_content: str = Field(..., min_length=1)
    version: str = "1.0.0"
    metadata_json: Optional[Dict[str, Any]] = None


class SkillUpdate(BaseModel):
    """Skill update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    md_content: Optional[str] = None
    category: Optional[str] = None
    permission_level: Optional[str] = None
    requires_approval: Optional[bool] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class SkillResponse(BaseModel):
    """Skill response schema."""
    id: int
    name: str
    description: Optional[str]
    version: str
    category: Optional[str]
    permission_level: Optional[str] = None
    requires_approval: Optional[bool] = False
    is_active: bool
    metadata_json: Optional[Dict[str, Any]]
    tags: Optional[List[str]] = None
    md_content: Optional[str] = None
    bundle_file_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillListResponse(BaseModel):
    """Paginated skill list response."""
    total: int
    skills: list[SkillResponse]


class ToolBase(BaseModel):
    """Base tool schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    permission_level: str = "medium"
    requires_approval: bool = False
    is_active: bool = True
    command_template: Optional[str] = None
    input_schema_json: Optional[str] = None
    timeout_seconds: int = 60
    required_permission: Optional[str] = None
    tags: Optional[List[str]] = None


class ToolCreate(ToolBase):
    """Tool creation schema."""
    md_content: Optional[str] = None
    version: str = "1.0.0"
    metadata_json: Optional[Dict[str, Any]] = None


class ToolUpdate(BaseModel):
    """Tool update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    md_content: Optional[str] = None
    category: Optional[str] = None
    permission_level: Optional[str] = None
    requires_approval: Optional[bool] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[Dict[str, Any]] = None
    command_template: Optional[str] = None
    input_schema_json: Optional[str] = None
    timeout_seconds: Optional[int] = None
    required_permission: Optional[str] = None
    tags: Optional[List[str]] = None


class ToolResponse(BaseModel):
    """Tool response schema."""
    id: int
    name: str
    description: Optional[str]
    version: str
    category: Optional[str]
    permission_level: str
    requires_approval: bool
    is_active: bool
    metadata_json: Optional[Dict[str, Any]]
    md_content: Optional[str] = None
    command_template: Optional[str] = None
    input_schema_json: Optional[str] = None
    timeout_seconds: int = 60
    required_permission: Optional[str] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Aliases
SkillRead = SkillResponse
ToolRead = ToolResponse
class ToolListResponse(BaseModel):
    """Paginated tool list response."""
    total: int
    tools: list[ToolResponse]


class SkillInstallUrlRequest(BaseModel):
    """Request to install a skill from a URL."""
    url: str = Field(..., description="Raw URL pointing to a skill markdown file")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Optional HTTP headers (e.g. Authorization)")


class SkillImportFailure(BaseModel):
    """One skill inside a bundle that could not be installed."""
    name: Optional[str] = None
    error: str


class SkillInstallResponse(BaseModel):
    """Response after installing one or more skills.

    ``skill`` stays populated for single-skill imports so existing callers keep
    working; bundle imports report every result through ``installed``/``failed``.
    """
    success: bool
    skill: Optional[SkillRead] = None
    installed: List[SkillRead] = Field(default_factory=list)
    failed: List[SkillImportFailure] = Field(default_factory=list)
    error: Optional[str] = None


class SkillFileRead(BaseModel):
    """Metadata for one bundled skill file (never the content itself)."""
    path: str
    size_bytes: int
    mime: Optional[str] = None
    is_binary: bool = False

    model_config = ConfigDict(from_attributes=True)


class SkillFileListResponse(BaseModel):
    """All bundled files belonging to a skill."""
    skill_id: int
    total: int
    files: List[SkillFileRead]
