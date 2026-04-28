"""Skill and Tool database models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from app.core.database import Base


class Skill(Base):
    """Skill model for skill pool management."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    md_content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0.0")
    category = Column(String(50), nullable=True)  # threat_intel, log_analysis, etc.
    permission_level = Column(String(20), default="medium")
    requires_approval = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Skill {self.name} (v{self.version})>"


class Tool(Base):
    """Tool model for tool pool management."""

    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    md_content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0.0")
    category = Column(String(50), nullable=True)
    permission_level = Column(String(20), default="medium")
    requires_approval = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Tool {self.name} (v{self.version})>"