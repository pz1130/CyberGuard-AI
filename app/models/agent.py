"""Agent configuration database models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class AgentConfig(Base):
    """Sub-agent configuration model."""

    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(100), unique=True, nullable=False, index=True)
    backend_type = Column(String(50), nullable=False)  # openclaw, hermes, custom
    provider_id = Column(String(100), nullable=True)
    endpoint_url = Column(String(500), nullable=True)
    env_vars_encrypted = Column(Text, nullable=True)  # AES-256 encrypted JSON
    system_prompt = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    permission_level = Column(String(20), default="medium")  # low, medium, high
    associated_skills = Column(JSON, nullable=True)  # List of skill IDs
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentConfig {self.agent_name} ({self.backend_type})>"


class AgentExecution(Base):
    """Agent execution/Task tracking model."""

    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    agent_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=False)
    status = Column(String(20), nullable=False)  # pending, running, completed, failed
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentExecution {self.execution_id} ({self.status})>"