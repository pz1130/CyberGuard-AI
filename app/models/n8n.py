"""N8N connection and workflow models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from app.core.database import Base


class N8NConnection(Base):
    """N8N instance connection configuration."""

    __tablename__ = "n8n_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<N8NConnection {self.name} ({self.base_url})>"
