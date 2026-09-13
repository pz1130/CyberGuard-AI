"""Backup manifest database model."""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text
from app.core.database import Base
from app.core.time import utc_now


class BackupRecord(Base):
    """Backup manifest record for persistence."""

    __tablename__ = "backup_records"

    id = Column(String(36), primary_key=True)  # UUID as string
    created_at = Column(DateTime, default=utc_now, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    format = Column(String(50), nullable=False, default="pg_dump.custom.aes")
    local_path = Column(String(500), nullable=True)
    remote_url = Column(String(1000), nullable=True)
    s3_bucket = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending/completed/failed/expired
    error = Column(Text, nullable=True)
    retention_days = Column(Integer, nullable=False, default=30)

    def __repr__(self):
        return f"<BackupRecord {self.id} ({self.status})>"
