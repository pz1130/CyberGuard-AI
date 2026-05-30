"""Pydantic schemas for webhook configuration."""
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Events that outgoing webhooks may subscribe to. Keep this list as the
# single source of truth — service code rejects unknown events.
SUPPORTED_EVENTS = ("approval.required",)


class WebhookBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    direction: Literal["incoming", "outgoing"]
    description: Optional[str] = None
    is_active: bool = True

    # Outgoing fields
    outgoing_url: Optional[str] = Field(
        default=None,
        max_length=1024,
        description="Target URL (http/https). Required when direction='outgoing'.",
    )
    outgoing_events: Optional[List[str]] = Field(
        default=None,
        description=f"Subscribed event names. Allowed: {list(SUPPORTED_EVENTS)}.",
    )

    @field_validator("outgoing_url")
    @classmethod
    def _check_url(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("outgoing_url must start with http:// or https://")
        return v

    @field_validator("outgoing_events")
    @classmethod
    def _check_events(cls, v):
        if v is None:
            return v
        bad = [e for e in v if e not in SUPPORTED_EVENTS]
        if bad:
            raise ValueError(
                f"Unknown events {bad}. Allowed: {list(SUPPORTED_EVENTS)}"
            )
        return list(dict.fromkeys(v))  # dedupe, preserve order


class WebhookCreate(WebhookBase):
    """Create a webhook.

    direction=incoming → server generates a single-use plaintext token
                         and returns it once (no plaintext stored).
    direction=outgoing → optionally supply `outgoing_secret` for HMAC signing.
    """
    outgoing_secret: Optional[str] = Field(
        default=None,
        max_length=200,
        description="HMAC signing secret (AES-256 encrypted at rest). Optional.",
    )


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    outgoing_url: Optional[str] = None
    outgoing_events: Optional[List[str]] = None
    outgoing_secret: Optional[str] = None

    @field_validator("outgoing_url")
    @classmethod
    def _check_url(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("outgoing_url must start with http:// or https://")
        return v

    @field_validator("outgoing_events")
    @classmethod
    def _check_events(cls, v):
        if v is None:
            return v
        bad = [e for e in v if e not in SUPPORTED_EVENTS]
        if bad:
            raise ValueError(
                f"Unknown events {bad}. Allowed: {list(SUPPORTED_EVENTS)}"
            )
        return list(dict.fromkeys(v))


class WebhookRead(BaseModel):
    id: int
    name: str
    direction: str
    description: Optional[str]
    is_active: bool
    # Incoming
    has_token: bool = False
    incoming_url: Optional[str] = None  # populated by router with base URL
    # Outgoing
    outgoing_url: Optional[str]
    outgoing_events: Optional[List[str]]
    has_secret: bool = False
    # Stats
    last_triggered_at: Optional[datetime]
    trigger_count: int
    success_count: int
    failure_count: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    # Set only on create / regenerate to deliver plaintext token once.
    plaintext_token: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_url(cls, obj, base_url: str = "") -> "WebhookRead":
        inst = cls.model_validate(obj)
        inst.has_token = bool(obj.incoming_token_hash)
        inst.has_secret = bool(obj.outgoing_secret_encrypted)
        # Note: actual token plaintext is NOT recovered here — only the URL stub.
        if obj.direction == "incoming":
            inst.incoming_url = f"{base_url}/api/v1/webhooks/incoming/<TOKEN>"
        return inst


class WebhookListResponse(BaseModel):
    total: int
    webhooks: List[WebhookRead]


class WebhookTestRequest(BaseModel):
    """Fire a synthetic event to an outgoing webhook for verification."""
    sample_event: Optional[str] = Field(default="approval.required")


class WebhookTestResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
