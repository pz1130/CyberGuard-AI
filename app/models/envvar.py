"""Database models for environment variables."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.core.database import Base
from app.core.time import utc_now


class EnvVar(Base):
    """System-level environment variable (encrypted value)."""
    __tablename__ = "env_vars"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(200), unique=True, nullable=False, index=True)
    value_encrypted = Column(Text, nullable=False)  # AES-256 encrypted
    value_type = Column(String(20), nullable=False, default="text")  # text | secret
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def __repr__(self):
        return f"<EnvVar {self.key} ({self.value_type})>"
