"""Persisted agent audit event (see migration 032)."""
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class AgentRunEvent(Base):
    """One event from ``agent_core.events.AuditBus``, chained per run.

    Append-only: rows are never updated or deleted in normal operation, which
    is what makes ``prev_hash`` / ``entry_hash`` meaningful as tamper evidence.
    """

    __tablename__ = "agent_run_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    agent_id = Column(Integer, nullable=True)
    conversation_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    layer = Column(String(32), nullable=False)
    phase = Column(String(16), nullable=False)
    name = Column(String(120), nullable=False)
    turn_id = Column(String(64), nullable=True)
    tool_call_id = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=True)
    replay = Column(String(10), nullable=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
