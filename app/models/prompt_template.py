"""Prompt Template model.

User-defined reusable system prompts that can be picked from the Chat
"CUSTOM SYSTEM PROMPT" panel (and other prompt-override fields).

`category` lets the UI filter templates by which prompt slot they target:
  - "system"        : Master Agent system prompt override
  - "intent_parser" : Intent-parser prompt override
  - "summarizer"    : Summarizer prompt override
  - "general"       : Re-usable in any slot
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, CheckConstraint
from app.core.database import Base


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    category = Column(String(32), nullable=False, default="general")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('system', 'intent_parser', 'summarizer', 'general')",
            name="ck_prompt_templates_category",
        ),
    )
