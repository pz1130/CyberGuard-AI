"""Pydantic schemas for environment variables."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class EnvVarBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    value_type: str = Field(default="text")  # text | secret
    description: Optional[str] = None
    is_active: bool = True


class EnvVarCreate(EnvVarBase):
    """Create env var — value is provided in plaintext here, encrypted before DB write."""
    value: str = Field(..., description="Plaintext value (encrypted before storage)")


class EnvVarUpdate(BaseModel):
    """Update env var."""
    value: Optional[str] = None
    value_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class EnvVarRead(BaseModel):
    """Read env var — NEVER returns plaintext value."""
    id: int
    key: str
    value_type: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EnvVarListResponse(BaseModel):
    total: int
    vars: list[EnvVarRead]
