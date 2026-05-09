"""Pydantic schemas for backup and restore operations."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class BackupConfigBase(BaseModel):
    """Base backup configuration schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    backup_type: str = Field(..., description="full, incremental, differential")
    retention_days: int = 30


class BackupConfigCreate(BackupConfigBase):
    """Backup configuration creation schema."""
    schedule_cron: str = Field(..., description="Cron expression for scheduled backups")
    target_path: str
    compress: bool = True
    encrypt: bool = True


class BackupConfigUpdate(BaseModel):
    """Backup configuration update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    backup_type: Optional[str] = None
    schedule_cron: Optional[str] = None
    retention_days: Optional[int] = None
    target_path: Optional[str] = None
    compress: Optional[bool] = None
    encrypt: Optional[bool] = None
    is_active: Optional[bool] = None


class BackupConfigResponse(BaseModel):
    """Backup configuration response schema."""
    id: int
    name: str
    description: Optional[str]
    backup_type: str
    schedule_cron: str
    retention_days: int
    target_path: str
    compress: bool
    encrypt: bool
    is_active: bool
    last_backup_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BackupExecutionResponse(BaseModel):
    """Backup execution response schema."""
    execution_id: str
    config_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    file_size: Optional[int] = None
    file_count: Optional[int] = None
    error: Optional[str] = None


class RestoreRequest(BaseModel):
    """Restore request schema."""
    backup_id: str
    target_path: Optional[str] = None
    overwrite: bool = False
    confirm: bool = Field(
        default=False,
        description="Must be True to acknowledge that restore will overwrite the current database state"
    )


class RestoreResponse(BaseModel):
    """Restore operation response schema."""
    execution_id: str
    backup_id: str
    status: str
    restored_files: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str] = None


class BackupListResponse(BaseModel):
    """Paginated backup list response."""
    total: int
    backups: List[Dict[str, Any]]

# Aliases
BackupRequest = BackupConfigCreate
BackupResponse = BackupExecutionResponse


class BackupRecord(BaseModel):
    """Backup record schema for reading from DB."""
    id: str
    created_at: datetime
    size_bytes: int
    format: str = "pg_dump.custom.aes"
    local_path: Optional[str] = None
    remote_url: Optional[str] = None
    s3_bucket: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None
    retention_days: int = 30

    class Config:
        from_attributes = True
