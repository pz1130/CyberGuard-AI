"""One chat message, chained to the previous message in its conversation.

Append-only: rows are never updated or deleted in normal operation, which is
what makes ``prev_hash`` / ``entry_hash`` meaningful as evidence. Deleting a
conversation from the UI sets ``conversations.deleted_at`` and leaves these
rows alone (see ``app/routers/conversations.py``).
"""
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint, false,
)

from app.core.database import Base
from app.core.time import utc_now


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        # Not merely an index: it is what stops two API workers that computed
        # the same seq from writing a forked chain that still verifies.
        UniqueConstraint("conversation_id", "seq", name="uq_conv_messages_seq"),
        Index("ix_conv_messages_conv_seq", "conversation_id", "seq"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    seq = Column(Integer, nullable=False)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    # Ties a message to the tool-level evidence already in agent_run_events.
    run_id = Column(String(64), nullable=True)
    turn_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    # Outside the hash on purpose: provenance, not content. See conversation_chain.
    backfilled = Column(Boolean, nullable=False, default=False, server_default=false())
    prev_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False)
