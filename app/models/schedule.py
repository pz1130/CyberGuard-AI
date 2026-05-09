"""Scheduled tasks database model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from app.core.database import Base


class ScheduledTask(Base):
    """Scheduled task model for cron jobs."""

    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID string
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    cron_expression = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False)  # agent_execution, backup, report_generation
    agent_id = Column(Integer, nullable=True)
    task_config = Column(JSON, nullable=True, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ScheduledTask {self.name} ({self.task_type})>"
