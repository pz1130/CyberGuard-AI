"""Chat conversation model."""
from datetime import datetime
from sqlalchemy import Column, Index, Integer, String, Text, DateTime, ForeignKey, Float
from app.core.database import Base


class Conversation(Base):
    """Chat conversation for persistent history and per-conversation agent config."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conv_agent", "agent_id", "parent_conversation_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), default="新对话")
    messages_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Per-conversation agent config overrides
    system_prompt_override = Column(Text, nullable=True)
    intent_parser_prompt_override = Column(Text, nullable=True)
    summarizer_prompt_override = Column(Text, nullable=True)
    model_override = Column(String(100), nullable=True)
    temperature_override = Column(Float, nullable=True)

    # Knowledge base for RAG
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True)

    # Internal-agent memory slice: when agent_id is set, this row stores the
    # message history for that internal agent under a parent (Master) conversation.
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=True)
    parent_conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
