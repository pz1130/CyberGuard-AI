"""Group chat message persistence model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


class GroupChatMessage(Base):
    """Persisted group chat message for history and audit trail."""

    __tablename__ = "group_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)  # null for anonymous/guest
    username = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    # Raw metadata stored at insert time (source client info, etc.)
    metadata_json = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # FK to users table (optional — allow null for system messages)
    # Using nullable FK without ondelete to avoid breaking guests
    __table_args__ = (
        Index("ix_group_chat_messages_room_created", "room_id", "created_at"),
    )

    def __repr__(self):
        return f"<GroupChatMessage room={self.room_id} user={self.username} at {self.created_at}>"
