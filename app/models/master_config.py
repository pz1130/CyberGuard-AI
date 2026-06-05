"""Master Agent configuration model."""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, Float, Text, DateTime
from typing import Optional
from app.core.database import Base


class MasterAgentConfig(Base):
    """Master Agent configuration for system prompts and model settings."""

    __tablename__ = "master_agent_config"

    id = Column(Integer, primary_key=True)
    llm_provider_id = Column(Integer, nullable=True)
    llm_model = Column(String(100), nullable=True)
    system_prompt = Column(Text, nullable=True)
    temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)
    context_compression_enabled = Column(Boolean, nullable=False, default=True)
    compression_model = Column(String(100), nullable=True)
    compression_max_tokens = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Master agent behavior (prompts + limits)
    intent_parser_prompt = Column(Text, nullable=True)
    summarizer_prompt = Column(Text, nullable=True)
    max_rounds = Column(Integer, nullable=True)
    auto_approve_threshold = Column(Integer, nullable=True, default=0)
    # Branding
    branding_logo: Optional[str] = Column(Text, nullable=True)  # data:image/...;base64,...
    branding_company_name: Optional[str] = Column(String(100), nullable=True)