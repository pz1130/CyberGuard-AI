"""Master Agent configuration model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from app.core.database import Base


class MasterAgentConfig(Base):
    """Master Agent configuration for system prompts and model settings."""

    __tablename__ = "master_agent_config"

    id = Column(Integer, primary_key=True)
    model = Column(String(100), default="gpt-4o")
    temperature = Column(Float, default=0.7)
    system_prompt = Column(Text, nullable=False)
    intent_parser_prompt = Column(Text, nullable=False)
    summarizer_prompt = Column(Text, nullable=False)
    max_rounds = Column(Integer, default=10)
    auto_approve_threshold = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)