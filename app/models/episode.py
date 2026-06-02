"""Episodic memory model — one row per recorded agent run (success reuse).

The service (app/services/episodic_memory.py) reads/writes via raw SQL for the
pgvector ANN path; this model exists for metadata completeness and ORM access.
See: docs/superpowers/specs/2026-06-02-episodic-memory-design.md
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, Index
from pgvector.sqlalchemy import Vector

from app.core.database import Base

EPISODE_EMBED_DIM = 1536


class AgentEpisode(Base):
    """A distilled record of which approach succeeded for which task."""

    __tablename__ = "agent_episodes"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    task_text = Column(Text, nullable=False)
    task_embedding = Column(Vector(EPISODE_EMBED_DIM), nullable=False)
    approach = Column(Text, nullable=True)            # ordered tool names
    outcome = Column(Text, nullable=True)             # truncated final answer
    success = Column(Boolean, nullable=False, default=True, index=True)
    tool_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_agent_episodes_agent_success", "agent_id", "success"),
    )

    def __repr__(self):
        return f"<AgentEpisode agent={self.agent_id} success={self.success}>"
