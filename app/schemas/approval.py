"""Pydantic schemas for approval requests."""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class ApprovalRequestCreate(BaseModel):
    """Schema for creating an approval request (internal use by MasterAgent)."""
    request_id: str
    user_id: int
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    action_type: str
    action_description: str
    payload: Optional[Dict[str, Any]] = None
    risk_level: str = "medium"  # low / medium / high / critical
    urgency: str = "normal"      # normal / urgent
    expires_in_minutes: Optional[int] = 60  # None = no expiry


class ApprovalRequestResponse(BaseModel):
    """Schema for an approval request in list/detail views."""
    id: int
    request_id: str
    user_id: int
    approver_id: Optional[int]
    agent_id: Optional[int]
    agent_name: Optional[str]
    action_type: str
    action_description: str
    payload: Optional[Dict[str, Any]]
    risk_level: str
    urgency: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime]
    decided_at: Optional[datetime]
    approver_comment: Optional[str]

    class Config:
        from_attributes = True


class ApprovalDecision(BaseModel):
    """Schema for approving or rejecting a request."""
    decision: str  # "approved" or "rejected"
    comment: Optional[str] = None


class ApprovalListResponse(BaseModel):
    """Schema for listing approval requests."""
    requests: list[ApprovalRequestResponse]
    total: int
