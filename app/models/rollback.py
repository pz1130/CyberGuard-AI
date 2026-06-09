"""Rollback registration model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.core.database import Base


class RollbackRegistration(Base):
    __tablename__ = "rollback_registrations"
    id = Column(Integer, primary_key=True, index=True)
    action_id = Column(String(36), unique=True, nullable=False, index=True)
    tool_id = Column(Integer, nullable=True)
    tool_name = Column(String(100), nullable=True)
    rollback_argv = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="registered")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    reverted_at = Column(DateTime, nullable=True)
    detail = Column(String(500), nullable=True)
