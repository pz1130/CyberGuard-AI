"""Backup management router."""
import uuid
import os
import subprocess
import io
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db_session
from app.core.dependencies import require_role
from app.core.rbac import Role
from app.core.security import encrypt_data, decrypt_data
from app.config import settings
from app.schemas.backup import BackupRequest, BackupResponse, RestoreRequest, RestoreResponse, BackupRecord
from app.models.backup import BackupRecord as BackupRecordModel

router = APIRouter()

BACKUP_DIR = os.environ.get("CYBERGUARD_BACKUP_DIR", "/backups")
MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5MB
PART_SIZE = 10 * 1024 * 1024  # 10MB
MAX_PARTS = 10000

logger = logging.getLogger(__name__)


def _ensure_backup_dir():
    """Ensure backup directory exists."""
    os.makedirs(BACKUP_DIR, exist_ok=True)


async def _run_pg_dump(exclude_tables: list[str] = None) -> bytes:
    """Run pg_dump and return compressed output.
    exclude_tables: optional list of table names to exclude *data* only (using --exclude-table-data).
    Schema is still included so that restore keeps the tables (empty).
    """
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    cmd = ["pg_dump", "--dbname", db_url, "--format=custom", "--compress=6"]
    if exclude_tables:
        for table in exclude_tables:
            cmd.extend(["--exclude-table-data", table])  # exclude data only; keep table schema so restore doesn't drop it permanently
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {stderr.decode()}")
    return stdout


async def _run_psql_restore(dump_path: str):
    """Restore database from pg_dump custom format."""
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    with open(dump_path, "rb") as f:
        data = f.read()
    proc = await asyncio.create_subprocess_exec(
        "pg_restore", "--dbname", db_url, "--clean", "--if-exists",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(input=data), timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"pg_restore failed: {stderr.decode()}")


def _encrypt_dump(data: bytes) -> bytes:
    """Encrypt binary dump with AES-256 (base64-encode first for text cipher compatibility)."""
    import base64
    from app.core.security import encrypt_data
    encoded = base64.b64encode(data).decode("ascii")
    return encrypt_data(encoded).encode("utf-8")


def _decrypt_dump(data: bytes) -> bytes:
    """Decrypt AES-256 encrypted dump back to original binary."""
    import base64
    from app.core.security import decrypt_data
    encoded = decrypt_data(data.decode("utf-8"))
    return base64.b64decode(encoded)


async def asyncio_write_file(path: str, data: bytes):
    """Write bytes to file (sync wrapper for use in async context)."""
    with open(path, "wb") as f:
        f.write(data)


def _validate_s3_endpoint(endpoint: str) -> str:
    """Validate S3 endpoint URL for SSRF protection."""
    from urllib.parse import urlparse
    if not endpoint:
        raise ValueError("S3 endpoint cannot be empty")
    
    parsed = urlparse(endpoint)
    scheme = parsed.scheme.lower()
    
    # Only allow https for S3-compatible services
    if scheme not in ("https", "s3", "oss"):
        raise ValueError(f"Disallowed endpoint scheme: {scheme}")
    
    hostname = parsed.hostname or ""
    
    # Block private network ranges, localhost, and metadata endpoints
    blocked = (
        "169.254.169.254",  # AWS metadata
        "metadata.google.internal",  # GCP metadata
        "metadata.internal",
        "localhost",
        "0.0.0.0",
        "127.0.0.1",
    )
    # Block AWS S3 regional endpoints that could be internal
    if hostname.endswith(".amazonaws.com") and ".internal" in hostname:
        raise ValueError(f"Disallowed internal AWS endpoint: {hostname}")
    
    if any(hostname == h or hostname.endswith(f".{h}") for h in blocked):
        raise ValueError(f"Disallowed host: {hostname}")
    
    # Basic IP range blocking (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
    import ipaddress
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass  # Not an IP address, hostname-based checks above suffice
    else:
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            raise ValueError(f"Disallowed private IP: {hostname}")
    
    return endpoint


async def _upload_to_s3_multipart(data: bytes, bucket: str, key: str) -> str:
    """Upload data to S3 using multipart upload for large files."""
    import boto3
    from botocore.config import Config
    import asyncio

    s3_endpoint = os.environ.get("S3_ENDPOINT", os.environ.get("OSS_ENDPOINT", ""))
    s3_access_key = os.environ.get("S3_ACCESS_KEY", "")
    s3_secret_key = os.environ.get("S3_SECRET_KEY", "")
    s3_region = os.environ.get("S3_REGION", "us-east-1")

    if not s3_endpoint or not s3_access_key:
        raise RuntimeError("S3/OSS not configured: set S3_ENDPOINT and S3_ACCESS_KEY env vars")

    # Validate endpoint for SSRF protection
    _validate_s3_endpoint(s3_endpoint)

    # Block path traversal
    if ".." in bucket or bucket.startswith("/") or not bucket:
        raise ValueError("Invalid bucket name")
    if ".." in key or key.startswith("/"):
        raise ValueError("Invalid S3 key")

    endpoint_url = f"{s3_endpoint}/{bucket}"

    data_len = len(data)

    # For small files or if multipart fails, fall back to regular upload
    if data_len <= MULTIPART_THRESHOLD:
        return await _upload_to_s3_small(data, bucket, key, s3_access_key, s3_secret_key, s3_region, s3_endpoint)

    # Initiate multipart upload (run sync boto3 in thread to avoid blocking event loop)
    def _do_initiate():
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
            config=Config(signature_version="s3v4"),
        )
        return client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType="application/octet-stream",
        )

    try:
        response = await asyncio.to_thread(_do_initiate)
        upload_id = response["UploadId"]
    except Exception as e:
        logger.warning(f"Multipart initiation failed, falling back to regular upload: {e}")
        return await _upload_to_s3_small(data, bucket, key, s3_access_key, s3_secret_key, s3_region, s3_endpoint)

    # Upload parts
    parts = []
    part_number = 1
    offset = 0

    def _do_upload_part(part_number, chunk):
        import hashlib
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
        )
        md5_hash = __import__('base64').b64encode(hashlib.md5(chunk).digest()).decode()
        return client.upload_part(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=chunk,
            ContentMD5=md5_hash,
        )

    try:
        while offset < data_len:
            chunk_size = min(PART_SIZE, data_len - offset)
            chunk = data[offset:offset + chunk_size]

            response = await asyncio.to_thread(_do_upload_part, part_number, chunk)

            parts.append({
                "PartNumber": part_number,
                "ETag": response["ETag"],
            })

            offset += chunk_size
            part_number += 1

            if part_number > MAX_PARTS:
                raise RuntimeError(f"Too many parts ({part_number}), maximum is {MAX_PARTS}")

        # Complete multipart upload
        def _do_complete():
            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=s3_access_key,
                aws_secret_access_key=s3_secret_key,
                region_name=s3_region,
            )
            return client.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

        await asyncio.to_thread(_do_complete)

        return f"{s3_endpoint}/{bucket}/{key}"

    except Exception as e:
        # Abort multipart upload on failure (best effort)
        try:
            def _do_abort():
                client = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=s3_access_key,
                    aws_secret_access_key=s3_secret_key,
                    region_name=s3_region,
                )
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
            await asyncio.to_thread(_do_abort)
        except Exception:
            pass
        raise e


async def _upload_to_s3_small(data: bytes, bucket: str, key: str, s3_access_key: str, s3_secret_key: str, s3_region: str, s3_endpoint: str) -> str:
    """Regular S3 PUT upload for small files (run sync boto3 in thread pool)."""
    import boto3
    import asyncio

    def _do_put():
        client = boto3.client(
            "s3",
            endpoint_url=f"{s3_endpoint}/{bucket}",
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
        )
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="application/octet-stream",
        )

    await asyncio.to_thread(_do_put)
    return f"{s3_endpoint}/{bucket}/{key}"


async def _upload_to_s3(data: bytes, bucket: str, key: str) -> str:
    """Upload encrypted dump to S3-compatible storage.
    
    Uses multipart upload for files > 5MB, regular PUT otherwise.
    """
    return await _upload_to_s3_multipart(data, bucket, key)


async def _download_from_s3(url: str) -> bytes:
    """Download encrypted dump from S3-compatible storage."""
    import httpx
    from urllib.parse import urlparse
    
    # SSRF protection: validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "s3", "oss"):
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")
    if ".." in url:
        raise ValueError("Path traversal detected in URL")
    
    hostname = parsed.hostname or ""
    blocked = (
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.internal",
        "localhost",
        "0.0.0.0",
    )
    if any(hostname == h or hostname.endswith(f".{h}") for h in blocked):
        raise ValueError(f"Disallowed host: {hostname}")
    
    s3_access_key = os.environ.get("S3_ACCESS_KEY", "")
    s3_secret_key = os.environ.get("S3_SECRET_KEY", "")
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url, auth=(s3_access_key, s3_secret_key))
    if resp.status_code != 200:
        raise RuntimeError(f"S3 download failed: {resp.status_code}")
    return resp.content


async def _delete_from_s3(url: str) -> bool:
    """Delete an object from S3-compatible storage."""
    import boto3
    import asyncio
    from urllib.parse import urlparse

    s3_endpoint = os.environ.get("S3_ENDPOINT", os.environ.get("OSS_ENDPOINT", ""))
    s3_access_key = os.environ.get("S3_ACCESS_KEY", "")
    s3_secret_key = os.environ.get("S3_SECRET_KEY", "")
    s3_region = os.environ.get("S3_REGION", "us-east-1")

    if not s3_endpoint:
        return False

    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/", 1)
    bucket = path_parts[0] if path_parts else ""
    key = path_parts[1] if len(path_parts) > 1 else ""

    if not bucket or not key:
        logger.warning(f"Could not parse bucket/key from URL: {url}")
        return False

    endpoint_url = f"{s3_endpoint}/{bucket}"

    def _do_delete():
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
        )
        client.delete_object(Bucket=bucket, Key=key)

    try:
        await asyncio.to_thread(_do_delete)
        return True
    except Exception as e:
        logger.error(f"Failed to delete from S3: {e}")
        return False


async def _cleanup_old_backups() -> int:
    """Clean up backups older than their retention period.

    Gets its own DB session to avoid request-scoped session issues.
    Returns the number of backups cleaned up.
    """
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        # Get all completed backups ordered by created_at
        result = await session.execute(
            select(BackupRecordModel)
            .where(BackupRecordModel.status == "completed")
            .order_by(BackupRecordModel.created_at.desc())
        )
        all_backups = list(result.scalars().all())

        if not all_backups:
            return 0

        # Never delete the most recent successful backup
        most_recent = all_backups[0]

        cleaned_count = 0
        now = datetime.utcnow()

        for backup in all_backups[1:]:  # Skip the most recent
            if backup.status != "completed":
                continue

            age_days = (now - backup.created_at).days
            if age_days > backup.retention_days:
                logger.info(f"Cleaning up backup {backup.id} (age: {age_days} days, retention: {backup.retention_days} days)")

                # Delete from S3 if remote_url exists
                if backup.remote_url:
                    deleted = await _delete_from_s3(backup.remote_url)
                    if deleted:
                        logger.info(f"Deleted {backup.id} from S3: {backup.remote_url}")
                    else:
                        logger.warning(f"Failed to delete {backup.id} from S3, skipping DB update")
                        continue

                # Update status in DB
                backup.status = "expired"
                await session.commit()
                cleaned_count += 1

        logger.info(f"[cleanup] Cleaned up {cleaned_count} expired backups")
        return cleaned_count


@router.post("/backup", response_model=BackupResponse)
async def create_backup(
    body: BackupRequest,
    _=Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Trigger a system backup.
    1. Runs pg_dump on the PostgreSQL database (optionally excluding chat data via --exclude-table-data)
    2. Encrypts with AES-256
    3. Saves locally (and optionally to S3/OSS)
    """
    _ensure_backup_dir()
    backup_id = str(uuid.uuid4())
    timestamp = datetime.utcnow()
    retention_days = body.retention_days if hasattr(body, "retention_days") and body.retention_days else 30
    exclude_chat = getattr(body, 'exclude_chat', False)

    # Create DB record first with pending status
    db_record = BackupRecordModel(
        id=backup_id,
        created_at=timestamp,
        size_bytes=0,
        format="pg_dump.custom.aes",
        status="pending",
        retention_days=retention_days,
    )
    session.add(db_record)
    await session.commit()

    try:
        # 1. pg_dump
        exclude_tables = ["conversations"] if exclude_chat else None
        dump_data = await _run_pg_dump(exclude_tables=exclude_tables)

        # 2. Encrypt
        encrypted_data = _encrypt_dump(dump_data)

        # 3. Determine location
        local_path = os.path.join(BACKUP_DIR, f"{backup_id}.dump.aes")
        remote_url: Optional[str] = None

        # Save locally
        await asyncio_write_file(local_path, encrypted_data)
        file_size = len(encrypted_data)

        # 4. Upload to S3/OSS if target specified
        if body.target:
            key = f"cyberguard-backups/{timestamp.strftime('%Y%m%d')}/{backup_id}.dump.aes"
            remote_url = await _upload_to_s3(encrypted_data, body.target, key)

        # Update DB record
        db_record.size_bytes = file_size
        db_record.format = "pg_dump.custom.aes"
        db_record.local_path = local_path
        db_record.remote_url = remote_url
        db_record.s3_bucket = body.target if body.target else None
        db_record.status = "completed"
        await session.commit()

        # Trigger background cleanup (own session, not tied to request)
        asyncio.create_task(_cleanup_old_backups())

        return BackupResponse(
            execution_id=backup_id,
            config_id=0,
            status="completed",
            started_at=timestamp,
            completed_at=datetime.utcnow(),
            file_size=file_size,
        )
    except Exception as e:
        db_record.status = "failed"
        db_record.error = str(e)
        await session.commit()
        
        return BackupResponse(
            execution_id=backup_id,
            config_id=0,
            status="failed",
            started_at=timestamp,
            completed_at=datetime.utcnow(),
            error=str(e),
        )


@router.get("/backup")
async def list_backups(
    _=Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """List all backups from DB."""
    result = await session.execute(
        select(BackupRecordModel).order_by(BackupRecordModel.created_at.desc())
    )
    records = result.scalars().all()
    
    # Convert to dict format for backward compatibility
    backups = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "size_bytes": r.size_bytes,
            "format": r.format,
            "local_path": r.local_path,
            "remote_url": r.remote_url,
            "s3_bucket": r.s3_bucket,
            "status": r.status,
            "error": r.error,
            "retention_days": r.retention_days,
        }
        for r in records
    ]
    
    return {"backups": backups}


@router.post("/backup/{backup_id}/restore", response_model=RestoreResponse)
async def restore_backup(
    backup_id: str,
    body: RestoreRequest,
    _=Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Restore from a backup.
    Downloads from S3/OSS if remote, then decrypts and runs pg_restore.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restore requires confirm=true to acknowledge data overwrite risk",
        )
    
    # Query from DB
    result = await session.execute(
        select(BackupRecordModel).where(BackupRecordModel.id == backup_id)
    )
    manifest = result.scalar_one_or_none()
    
    if not manifest:
        raise HTTPException(status_code=404, detail="Backup not found")

    execution_id = str(uuid.uuid4())
    started_at = datetime.utcnow()

    try:
        # 1. Get encrypted data
        if manifest.remote_url:
            encrypted_data = await _download_from_s3(manifest.remote_url)
        elif manifest.local_path:
            with open(manifest.local_path, "rb") as f:
                encrypted_data = f.read()
        else:
            raise RuntimeError("No backup data source available")

        # 2. Decrypt
        dump_data = _decrypt_dump(encrypted_data)

        # 3. Write to temp file for pg_restore
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
            tmp.write(dump_data)
            tmp_path = tmp.name

        try:
            # 4. Restore
            await _run_psql_restore(tmp_path)
        finally:
            os.unlink(tmp_path)

        return RestoreResponse(
            execution_id=execution_id,
            backup_id=backup_id,
            status="completed",
            started_at=started_at,
            completed_at=datetime.utcnow(),
        )
    except Exception as e:
        return RestoreResponse(
            execution_id=execution_id,
            backup_id=backup_id,
            status="failed",
            started_at=started_at,
            completed_at=datetime.utcnow(),
            error=str(e),
        )


@router.delete("/backup/{backup_id}")
async def delete_backup(
    backup_id: str,
    _=Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Delete a backup: removes the local encrypted dump, the remote S3/OSS
    object (best-effort), and the DB record.
    """
    result = await session.execute(
        select(BackupRecordModel).where(BackupRecordModel.id == backup_id)
    )
    manifest = result.scalar_one_or_none()

    if not manifest:
        raise HTTPException(status_code=404, detail="Backup not found")

    local_deleted = False
    remote_deleted = False
    warnings: list[str] = []

    # 1. Delete local encrypted dump if present
    if manifest.local_path:
        try:
            if os.path.exists(manifest.local_path):
                os.unlink(manifest.local_path)
                local_deleted = True
        except OSError as e:
            logger.warning(f"Failed to delete local backup file {manifest.local_path}: {e}")
            warnings.append(f"local file: {e}")

    # 2. Delete remote object (best-effort — never block record removal on it)
    if manifest.remote_url:
        try:
            remote_deleted = await _delete_from_s3(manifest.remote_url)
            if not remote_deleted:
                warnings.append("remote object could not be deleted (check S3 config)")
        except Exception as e:
            logger.warning(f"Failed to delete remote backup {manifest.remote_url}: {e}")
            warnings.append(f"remote object: {e}")

    # 3. Drop the DB record
    await session.delete(manifest)
    await session.commit()

    logger.info(f"Deleted backup {backup_id} (local={local_deleted}, remote={remote_deleted})")

    return {
        "id": backup_id,
        "status": "deleted",
        "local_deleted": local_deleted,
        "remote_deleted": remote_deleted,
        "warnings": warnings,
    }
