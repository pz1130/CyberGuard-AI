"""Append-only, hash-chained log of what an agent run actually did."""
from datetime import datetime

from sqlalchemy import (BigInteger, Column, DateTime, Integer, String,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class AgentRunEvent(Base):
    """One event in an agent run.

    Rows are only ever appended. `prev_hash`/`entry_hash` chain the events of a
    run so a gap or an edit is detectable, matching the audit_logs chain.
    """

    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    agent_id = Column(Integer, nullable=True)
    conversation_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    event_type = Column(String(40), nullable=False, index=True)
    payload = Column(JSONB, nullable=True)
    # "never" | "safe" | None — whether the action this row records may be
    # re-executed during recovery.
    replay = Column(String(10), nullable=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentRunEvent {self.run_id}#{self.seq} {self.event_type}>"
