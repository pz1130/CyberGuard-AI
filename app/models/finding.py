"""Findings and append-only evidence/review timeline."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from app.core.database import Base
from app.core.time import utc_now


class Finding(Base):
    __tablename__ = "findings"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    target = Column(String(1000), nullable=False)
    severity = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    remediation = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="pending", index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    source = Column(String(20), nullable=False, default="human")
    agent_id = Column(Integer)  # Historical provenance, survives agent deletion.
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)


class FindingEvent(Base):
    __tablename__ = "finding_events"
    id = Column(Integer, primary_key=True)
    finding_id = Column(Integer, ForeignKey("findings.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action = Column(String(30), nullable=False)
    note = Column(Text, nullable=False)
    evidence = Column(Text, nullable=False, default="")
    evidence_hash = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)
    audit_request_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
