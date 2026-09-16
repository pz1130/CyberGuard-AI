"""Security settings model (single-row configuration).

Only settings that something actually enforces live here. Encryption, RBAC and
audit logging were once columns on this table; they are invariants of the
product, not choices, and a switch that turns one of them off is a back door
with a label on it. `api_key_rotation_days` named a feature that was never
built. Migration 043 dropped all four.
"""
from sqlalchemy import Column, DateTime, Integer
from app.core.database import Base
from app.core.time import utc_now


class SecuritySettings(Base):
    __tablename__ = "security_settings"

    id = Column(Integer, primary_key=True)
    max_login_attempts = Column(Integer, default=5, nullable=False)
    session_timeout_minutes = Column(Integer, default=30, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
