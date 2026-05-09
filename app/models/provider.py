"""Provider database models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from app.core.database import Base


class Provider(Base):
    """AI provider configuration model."""

    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    provider_type = Column(String(50), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    base_url = Column(String(500), nullable=True)
    api_version = Column(String(50), nullable=True)
    models = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Provider {self.name} ({self.provider_type})>"