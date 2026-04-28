"""Pydantic schemas for LLM provider management."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ProviderBase(BaseModel):
    """Base provider schema."""
    name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(..., description="openai, anthropic, azure, custom")


class ProviderCreate(ProviderBase):
    """Provider creation schema."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    models: List[str] = Field(default_factory=lambda: ["gpt-4o"])
    is_active: bool = True
    metadata_json: Optional[Dict[str, Any]] = None


class ProviderUpdate(BaseModel):
    """Provider update schema."""
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    models: Optional[List[str]] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[Dict[str, Any]] = None


class ProviderResponse(BaseModel):
    """Provider response schema."""
    id: int
    name: str
    provider_type: str
    base_url: Optional[str]
    api_version: Optional[str]
    models: List[str]
    is_active: bool
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProviderListResponse(BaseModel):
    """Paginated provider list response."""
    total: int
    providers: List[ProviderResponse]


class ProviderTestRequest(BaseModel):
    """Provider connection test request schema."""
    provider_id: int
    test_model: Optional[str] = None


class ProviderTestResponse(BaseModel):
    """Provider connection test response schema."""
    success: bool
    latency_ms: Optional[float] = None
    model: Optional[str] = None
    error: Optional[str] = None
    response_preview: Optional[str] = None

# Aliases
ProviderRead = ProviderResponse
