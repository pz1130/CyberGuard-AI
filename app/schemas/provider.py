"""Pydantic schemas for LLM provider management."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any, Literal


class ModelInfo(BaseModel):
    """Model info with type classification and optional probed capabilities /
    verification status.

    `capabilities` is filled by the capability prober, e.g.
    {"tools": true, "vision": false, "probed_at": "2026-06-03T..."}. None until probed.

    `verified` is filled by /providers/test and /models/probe:
      None  — never tested
      True  — test succeeded
      False — test failed (see test_error for detail)

    `last_tested_at` is an ISO 8601 string (UTC, naive — matches the
    project's `datetime.utcnow()` convention; see also
    `tz-aware-timestamps-migration` memory note). Stored as `str` (not
    `datetime`) so the JSON column write sites (`provider.models = [m.model_dump()...]`)
    don't need a JSON encoder for datetime — asyncpg won't serialize it.
    """
    name: str
    model_type: Literal["chat", "embedding", "rerank"] = "chat"
    capabilities: Optional[Dict[str, Any]] = None
    verified: Optional[bool] = None
    last_tested_at: Optional[str] = None
    test_error: Optional[str] = None


class ProviderBase(BaseModel):
    """Base provider schema."""
    name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(..., description="openai, anthropic, azure, custom")


class ProviderCreate(ProviderBase):
    """Provider creation schema."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    models: List[ModelInfo] = Field(default_factory=lambda: [ModelInfo(name="gpt-4o", model_type="chat")])
    is_active: bool = True
    metadata_json: Optional[Dict[str, Any]] = None

    @field_validator("models", mode="before")
    @classmethod
    def convert_legacy_models(cls, v):
        """Accept both legacy ["gpt-4o"] and new [{"name": "gpt-4o", "model_type": "chat"}] formats."""
        if not v:
            return [ModelInfo(name="gpt-4o", model_type="chat")]
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [ModelInfo(name=m, model_type="chat") for m in v]
        return v


class ProviderUpdate(BaseModel):
    """Provider update schema."""
    name: Optional[str] = None
    provider_type: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    models: Optional[List[ModelInfo]] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[Dict[str, Any]] = None

    @field_validator("models", mode="before")
    @classmethod
    def convert_legacy_models(cls, v):
        if not v:
            return None
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [ModelInfo(name=m, model_type="chat") for m in v]
        return v


class ProviderResponse(BaseModel):
    """Provider response schema."""
    id: int
    name: str
    provider_type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_version: Optional[str] = None
    models: List[ModelInfo]
    is_active: bool
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("models", mode="before")
    @classmethod
    def convert_legacy_models(cls, v):
        if not v:
            return []
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [ModelInfo(name=m, model_type="chat") for m in v]
        return v


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
