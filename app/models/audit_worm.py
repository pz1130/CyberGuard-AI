"""Audit WORM export marker model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base


class AuditWormExport(Base):
    __tablename__ = "audit_worm_exports"
    id = Column(Integer, primary_key=True, index=True)
    last_audit_id = Column(Integer, nullable=False)
    object_key = Column(String(300), nullable=False)
    rows = Column(Integer, nullable=False)
    retain_until = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
