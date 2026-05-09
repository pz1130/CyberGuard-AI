"""Pydantic schemas for skill and tool management."""
from pydantic import BaseModel, Field
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
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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


class ToolCreate(ToolBase):
    """Tool creation schema."""
    md_content: str = Field(..., min_length=1)
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
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

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


class SkillInstallResponse(BaseModel):
    """Response after installing a skill."""
    success: bool
    skill: Optional[SkillRead] = None
    error: Optional[str] = None
