"""Security settings model (single-row configuration)."""
from sqlalchemy import Boolean, Column, DateTime, Integer
from app.core.database import Base
from app.core.time import utc_now


class SecuritySettings(Base):
    __tablename__ = "security_settings"

    id = Column(Integer, primary_key=True)
    encryption_enabled = Column(Boolean, default=True, nullable=False)
    rbac_enabled = Column(Boolean, default=True, nullable=False)
    audit_logging = Column(Boolean, default=True, nullable=False)
    max_login_attempts = Column(Integer, default=5, nullable=False)
    session_timeout_minutes = Column(Integer, default=30, nullable=False)
    api_key_rotation_days = Column(Integer, default=90, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
