"""Chat conversation model."""
from sqlalchemy import Column, Index, Integer, String, Text, DateTime, ForeignKey, Float
from app.core.database import Base
from app.core.time import utc_now


class Conversation(Base):
    """Chat conversation for persistent history and per-conversation agent config."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conv_agent", "agent_id", "parent_conversation_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # No placeholder is stored. A title the user has not set yet is absent, and
    # the UI renders its own translated placeholder — storing one would freeze
    # whatever language happened to be active when the row was created.
    title = Column(String(200), nullable=True, default=None)
    messages_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    # Immutability-first: the delete button tombstones the conversation rather
    # than destroying the transcript. Retention decides when rows really go.
    deleted_at = Column(DateTime, nullable=True, default=None)
    # Highest seq already written into the global audit chain by
    # app.services.conversation_anchor. -1 means "nothing anchored yet", which
    # is correct for a conversation whose first message will be seq 0.
    last_anchored_seq = Column(Integer, nullable=False, default=-1, server_default="-1")

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
