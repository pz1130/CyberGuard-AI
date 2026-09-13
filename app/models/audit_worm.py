"""Audit WORM export marker model."""
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base
from app.core.time import utc_now


class AuditWormExport(Base):
    __tablename__ = "audit_worm_exports"
    id = Column(Integer, primary_key=True, index=True)
    last_audit_id = Column(Integer, nullable=False)
    object_key = Column(String(300), nullable=False)
    rows = Column(Integer, nullable=False)
    retain_until = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, default=utc_now, nullable=False)
