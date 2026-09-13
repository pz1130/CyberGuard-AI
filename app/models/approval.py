"""Approval request database model."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from app.core.database import Base
from app.core.time import utc_now


class ApprovalRequest(Base):
    """Pending human approval request stored in DB."""

    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(36), unique=True, nullable=False, index=True)  # LangGraph request_id
    user_id = Column(Integer, nullable=False, index=True)                       # who triggered the request
    approver_id = Column(Integer, nullable=True)                                # who approved (filled on approve/reject)

    # What needs approval
    agent_id = Column(Integer, nullable=True)                                   # which sub-agent needs approval
    agent_name = Column(String(100), nullable=True)
    action_type = Column(String(50), nullable=False)                            # e.g. "delete", "execute", "deploy"
    action_description = Column(Text, nullable=True)                            # human-readable summary

    # Payload snapshot at time of request (JSON of sub-agent output / task plan)
    payload = Column(JSON, nullable=True, default=dict)

    # Risk & urgency
    risk_level = Column(String(20), default="medium")                            # low / medium / high / critical
    required_approver_role = Column(String(20), nullable=True)                   # min RBAC role to decide (A3 routing)
    required_approver_label = Column(String(100), nullable=True)                 # Standard's approver label (display)
    urgency = Column(String(20), default="normal")                              # normal / urgent

    # Status: pending / approved / rejected / expired / cancelled
    status = Column(String(20), default="pending", index=True)

    # Timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)                                 # auto-expire if set
    decided_at = Column(DateTime, nullable=True)

    # Approver comment
    approver_comment = Column(Text, nullable=True)

    def __repr__(self):
        return f"<ApprovalRequest {self.id} [{self.status}] {self.action_type}>"
