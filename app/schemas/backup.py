"""Pydantic schemas for backup and restore operations."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


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


class BackupRequest(BaseModel):
    """One-shot backup execution request from the WebUI."""
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Optional display name from the UI. Not persisted in MVP.",
    )
    description: Optional[str] = None
    backup_type: str = Field(
        default="full",
        description="Accepted for compatibility with the UI. Only full backups are supported in MVP.",
    )
    retention_days: int = Field(default=30, ge=1, le=3650)
    target: Optional[str] = Field(
        default=None,
        description="Optional S3/OSS bucket name for remote backup upload.",
    )
    exclude_chat: bool = Field(
        default=False,
        description="If true, exclude chat history (conversations table) from the backup for a configuration-only dump.",
    )


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

# Aliases for router compatibility
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

    model_config = ConfigDict(from_attributes=True)
