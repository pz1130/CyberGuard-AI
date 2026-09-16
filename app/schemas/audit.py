"""Pydantic schemas for audit logs."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime
from ipaddress import IPv6Address


class AuditLogResponse(BaseModel):
    """Audit log response schema."""
    id: int
    user_id: Optional[int]
    agent_id: Optional[str]
    action: str
    input_hash: str
    output_hash: str
    request_id: Optional[str]
    timestamp: datetime
    prev_hash: Optional[str] = None
    entry_hash: Optional[str] = None
    chain_version: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""
    total: int
    logs: List[AuditLogResponse]


class AuditLogQuery(BaseModel):
    """Audit log query parameters."""
    user_id: Optional[int] = None
    agent_id: Optional[str] = None
    action: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class AuditLogExportRequest(BaseModel):
    """Audit log export request schema."""
    start_date: datetime
    end_date: datetime
    format: str = "json"  # json, csv
    user_id: Optional[int] = None
    agent_id: Optional[str] = None

# Aliases
AuditLogRead = AuditLogResponse


class SyslogExportRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=514, ge=1, le=65535)
    protocol: Literal["udp", "tcp"] = "tcp"
    facility: int = Field(default=16, ge=0, le=23)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        value = value.strip()
        if not value or any(c.isspace() for c in value) or any(c in value for c in "/\\@?#"):
            raise ValueError("Use a hostname or IP address, without a URL or port")
        if ":" in value:
            try:
                IPv6Address(value)
            except ValueError as exc:
                raise ValueError("Enter the port separately") from exc
        return value
