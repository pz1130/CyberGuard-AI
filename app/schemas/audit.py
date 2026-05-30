"""Pydantic schemas for audit logs."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


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
