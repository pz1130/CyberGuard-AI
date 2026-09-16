"""A conversation mirrored to write-once storage.

One row per export. A conversation is re-exported as it grows, so several rows
may name the same conversation; the one with the highest ``head_seq`` is
current, and the older rows are kept because each names an object that still
exists in WORM storage and cannot be withdrawn.

Purging a conversation requires a row here whose ``head_seq`` equals the
conversation's last message — "exported at some point" is not enough, or a
conversation exported at seq 40 and since grown to seq 90 would lose fifty
messages that exist in no object.
"""
from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String,
)

from app.core.database import Base
from app.core.time import utc_now


class ConversationExport(Base):
    __tablename__ = "conversation_exports"
    __table_args__ = (
        Index("ix_conv_exports_conv", "conversation_id", "head_seq"),
    )

    id = Column(Integer, primary_key=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String(300), nullable=False)
    rows = Column(Integer, nullable=False)
    head_seq = Column(Integer, nullable=False)
    head_hash = Column(String(64), nullable=False)
    retain_until = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, nullable=False, default=utc_now)
