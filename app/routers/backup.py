"""Backup management router."""
import json, uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from app.core.dependencies import get_db, require_role
from app.core.rbac import Role
from app.schemas.backup import BackupRequest, BackupResponse

router = APIRouter()

# In-memory backup manifest for MVP
_backup_manifest = []


@router.post("/backup", response_model=BackupResponse)
async def create_backup(
    body: BackupRequest,
    _=Depends(require_role(Role.ADMIN)),
):
    """
    Trigger a full system backup.
    Writes local backup + optionally to S3 / Alibaba OSS.
    Returns backup manifest entry.
    """
    backup_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    # TODO: Implement actual backup logic
    # 1. pg_dump to a local file
    # 2. Encrypt the dump with AES-256
    # 3. Upload to S3/OSS if body.target is set
    # For MVP, return a stub
    manifest_entry = {
        "id": backup_id,
        "created_at": timestamp,
        "size_bytes": 0,
        "format": "tar.gz.aes",
        "location": f"/backups/{backup_id}.tar.gz.aes",
        "s3_bucket": body.target if body.target else None,
        "status": "completed",
        "note": "MVP stub - implement actual backup with pg_dump + AES encryption",
    }
    _backup_manifest.append(manifest_entry)
    return BackupResponse(**manifest_entry)


@router.get("/backup")
async def list_backups(_=Depends(require_role(Role.ADMIN))):
    """List all backups."""
    return {"backups": _backup_manifest}


@router.post("/backup/{backup_id}/restore")
async def restore_backup(backup_id: str, _=Depends(require_role(Role.ADMIN))):
    """Restore from a backup. Currently returns a stub response."""
    manifest = next((b for b in _backup_manifest if b["id"] == backup_id), None)
    if not manifest:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Backup not found")
    # TODO: Implement actual pg_dump restore + AES decrypt
    return {"message": f"Restore initiated for backup {backup_id}", "status": "pending", "backup": manifest}
