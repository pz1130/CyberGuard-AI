"""Audit log database model."""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.time import utc_now


class AuditLog(Base):
    """Audit log model for tracking all system actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    agent_id = Column(String(100), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    input_hash = Column(String(64), nullable=True)
    output_hash = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_path = Column(String(500), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    request_id = Column(String(36), nullable=True)
    # --- Standard "AI Agent Governance" audit fields (NDB Std v1.0 §Audit Trail) ---
    agent_name = Column(String(100), nullable=True)
    action_category = Column(String(20), nullable=True)   # observe|annotate|notify|contain_soft|contain_hard|remediate|mutate
    confidence = Column(String(10), nullable=True)         # stringified float (asyncpg JSON-safe convention)
    human_reviewer = Column(String(255), nullable=True)    # approver email/id or null
    rollback_possible = Column(Boolean, nullable=True)
    risk_tier = Column(String(20), nullable=True)          # critical|high|medium|low
    # --- Tamper-evidence hash chain ---
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True, index=True)
    chain_version = Column(Integer, nullable=True)

    # Relationship
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog user={self.user_id} action={self.action} at {self.timestamp}>"
