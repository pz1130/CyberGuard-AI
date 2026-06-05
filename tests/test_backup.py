"""Tests for the backup router's pure helpers + DB-backed retention logic.

backup.py was wholly untested.  The highest-value targets are the SSRF guards
(_validate_s3_endpoint / _download_from_s3), the encrypt/decrypt roundtrip, the
BackupRecord table roundtrip (catches model/migration column drift), and the
retention-cleanup state machine.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.backup import BackupRecord as BackupRecordModel
from app.routers import backup as bk


# --------------------------------------------------------------------------- #
# _validate_s3_endpoint — SSRF protection (pure)
# --------------------------------------------------------------------------- #

def test_validate_s3_endpoint_accepts_https():
    url = "https://s3.example.com"
    assert bk._validate_s3_endpoint(url) == url


def test_validate_s3_endpoint_accepts_s3_scheme():
    assert bk._validate_s3_endpoint("s3://bucket.example.com") == "s3://bucket.example.com"


def test_validate_s3_endpoint_rejects_empty():
    with pytest.raises(ValueError, match="cannot be empty"):
        bk._validate_s3_endpoint("")


@pytest.mark.parametrize("url", [
    "http://s3.example.com",   # plain http disallowed
    "ftp://s3.example.com",
    "file:///etc/passwd",
])
def test_validate_s3_endpoint_rejects_bad_scheme(url):
    with pytest.raises(ValueError, match="scheme"):
        bk._validate_s3_endpoint(url)


@pytest.mark.parametrize("url", [
    "https://localhost",
    "https://127.0.0.1",
    "https://169.254.169.254",          # AWS metadata
    "https://metadata.google.internal",  # GCP metadata
    "https://0.0.0.0",
])
def test_validate_s3_endpoint_rejects_blocked_hosts(url):
    with pytest.raises(ValueError):
        bk._validate_s3_endpoint(url)


@pytest.mark.parametrize("url", [
    "https://10.0.0.5",
    "https://192.168.1.10",
    "https://172.16.0.1",
])
def test_validate_s3_endpoint_rejects_private_ips(url):
    with pytest.raises(ValueError, match="private|Disallowed"):
        bk._validate_s3_endpoint(url)


# --------------------------------------------------------------------------- #
# _encrypt_dump / _decrypt_dump — binary roundtrip
# --------------------------------------------------------------------------- #

def test_encrypt_decrypt_roundtrip():
    blob = bytes(range(256)) * 8  # arbitrary binary, includes non-utf8 bytes
    encrypted = bk._encrypt_dump(blob)
    assert isinstance(encrypted, bytes)
    assert encrypted != blob
    assert bk._decrypt_dump(encrypted) == blob


def test_encrypt_decrypt_roundtrip_empty():
    assert bk._decrypt_dump(bk._encrypt_dump(b"")) == b""


# --------------------------------------------------------------------------- #
# _download_from_s3 — URL guards reject before any network call (async)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_download_rejects_bad_scheme():
    with pytest.raises(ValueError, match="scheme"):
        await bk._download_from_s3("http://example.com/backup.aes")


@pytest.mark.asyncio
async def test_download_rejects_path_traversal():
    with pytest.raises(ValueError, match="traversal"):
        await bk._download_from_s3("https://example.com/../../etc/passwd")


@pytest.mark.asyncio
async def test_download_rejects_blocked_host():
    with pytest.raises(ValueError, match="Disallowed host"):
        await bk._download_from_s3("https://localhost/backup.aes")


# --------------------------------------------------------------------------- #
# _delete_from_s3 — returns False (no-op) when S3 is not configured
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_delete_from_s3_unconfigured_returns_false(monkeypatch):
    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    monkeypatch.delenv("OSS_ENDPOINT", raising=False)
    assert await bk._delete_from_s3("https://s3.example.com/bucket/key") is False


# --------------------------------------------------------------------------- #
# BackupRecord table roundtrip + retention cleanup (real DB)
# --------------------------------------------------------------------------- #

@pytest.fixture
async def cleanup_backup_ids():
    ids: list[str] = []
    yield ids
    async with AsyncSessionLocal() as session:
        for bid in ids:
            await session.execute(
                delete(BackupRecordModel).where(BackupRecordModel.id == bid)
            )
        await session.commit()


async def _insert_backup(cleanup_backup_ids, *, created_at, status="completed",
                         retention_days=30, remote_url=None):
    bid = str(uuid.uuid4())
    cleanup_backup_ids.append(bid)
    async with AsyncSessionLocal() as session:
        session.add(BackupRecordModel(
            id=bid,
            created_at=created_at,
            size_bytes=123,
            format="pg_dump.custom.aes",
            status=status,
            retention_days=retention_days,
            remote_url=remote_url,
        ))
        await session.commit()
    return bid


async def _status_of(bid: str) -> str:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackupRecordModel).where(BackupRecordModel.id == bid)
        )
        return result.scalar_one().status


@pytest.mark.asyncio
async def test_backup_record_roundtrip(cleanup_backup_ids):
    bid = await _insert_backup(cleanup_backup_ids, created_at=datetime.utcnow())
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackupRecordModel).where(BackupRecordModel.id == bid)
        )
        rec = result.scalar_one()
    assert rec.size_bytes == 123
    assert rec.format == "pg_dump.custom.aes"
    assert rec.status == "completed"
    assert rec.retention_days == 30


@pytest.mark.asyncio
async def test_cleanup_expires_old_backup_but_keeps_fresh(cleanup_backup_ids):
    # A fresh backup (never expires) and an old one past its retention window.
    fresh = await _insert_backup(cleanup_backup_ids, created_at=datetime.utcnow())
    old = await _insert_backup(
        cleanup_backup_ids,
        created_at=datetime.utcnow() - timedelta(days=100),
        retention_days=30,
        remote_url=None,  # local-only → no S3 needed
    )

    cleaned = await bk._cleanup_old_backups()
    assert cleaned >= 1

    assert await _status_of(old) == "expired"
    # Fresh record is well within retention → still completed
    assert await _status_of(fresh) == "completed"
