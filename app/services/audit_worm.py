"""Mirror the hash-chained audit log to WORM object storage (NDB Std §Audit Trail).

Incremental, append-only export to an S3 Object-Lock bucket. Reuses the S3 env
config from app/routers/backup.py. Never mutates audit_logs.
"""
from __future__ import annotations
import asyncio
import json
import os
import hashlib
import base64
import time
import uuid
from types import SimpleNamespace
from datetime import timezone
from datetime import datetime, timedelta
from sqlalchemy import select
from app.core.time import utc_now

_FIELDS = ("id", "user_id", "agent_id", "agent_name", "action", "action_category",
           "confidence", "human_reviewer", "rollback_possible", "risk_tier",
           "input_hash", "output_hash", "request_id", "prev_hash", "entry_hash",
           "ip_address", "user_agent", "request_path", "metadata_json", "chain_version")


def _serialize_jsonl(rows) -> str:
    out = []
    for r in rows:
        rec = {f: getattr(r, f, None) for f in _FIELDS}
        rec["timestamp"] = getattr(r, "timestamp", None).isoformat() if getattr(r, "timestamp", None) else None
        out.append(json.dumps(rec, sort_keys=True, default=str))
    return "\n".join(out) + ("\n" if out else "")


async def _fetch_rows_after(after_id: int):
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    async with get_db_context() as s:
        return (await s.execute(select(AuditLog).where(AuditLog.id > after_id)
                                .order_by(AuditLog.id.asc()))).scalars().all()


async def _record_marker(last_id: int, key: str, rows: int, retain_until: datetime) -> None:
    from app.core.database import get_db_context
    from app.models.audit_worm import AuditWormExport
    async with get_db_context() as s:
        s.add(AuditWormExport(last_audit_id=last_id, object_key=key, rows=rows,
                              retain_until=retain_until, exported_at=utc_now()))
        await s.commit()


def _s3_client():
    import boto3
    from botocore.config import Config
    endpoint = os.environ.get("S3_ENDPOINT", os.environ.get("OSS_ENDPOINT", ""))
    access = os.environ.get("S3_ACCESS_KEY", "")
    secret = os.environ.get("S3_SECRET_KEY", "")
    region = os.environ.get("S3_REGION", "us-east-1")
    if not endpoint or not access:
        raise RuntimeError("S3/OSS not configured: set S3_ENDPOINT and S3_ACCESS_KEY")
    bucket = os.environ.get("AUDIT_WORM_BUCKET", "cyberguard-audit-worm")
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access,
                        aws_secret_access_key=secret, region_name=region,
                        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 0},
                                      s3={"addressing_style": "path"},
                                      request_checksum_calculation="when_required",
                                      response_checksum_validation="when_required")), bucket


async def _put_worm_object(key: str, data: bytes, retain_until: datetime) -> str:
    # S3 serializes retention dates at second precision. Round up so read-back
    # never appears shorter than the requested retention period.
    if retain_until.microsecond:
        retain_until = retain_until.replace(microsecond=0) + timedelta(seconds=1)
    def _do():
        client, bucket = _s3_client()
        uploaded = client.put_object(Bucket=bucket, Key=key, Body=data,
                          ContentMD5=base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode(),
                          ObjectLockMode="COMPLIANCE",
                          ObjectLockRetainUntilDate=retain_until,
                          Metadata={"sha256": hashlib.sha256(data).hexdigest()})
        version = uploaded.get('VersionId')
        if not version:
            raise RuntimeError('Archive storage did not return a version ID')
        retention = client.get_object_retention(Bucket=bucket, Key=key, VersionId=version)["Retention"]
        if not _retention_valid(retention, required_until=retain_until):
            raise RuntimeError("Archive retention lock was not confirmed")
        stored = client.get_object(Bucket=bucket, Key=key, VersionId=version)
        try:
            actual = stored["Body"].read(len(data) + 1)
        finally:
            stored["Body"].close()
        if hashlib.sha256(actual).digest() != hashlib.sha256(data).digest():
            raise RuntimeError("Archive read-back differs from uploaded evidence")
        return key
    return await asyncio.to_thread(_do)


class AuditExportBlocked(RuntimeError):
    pass


def _retention_valid(retention, *, required_until=None):
    until = retention.get('RetainUntilDate')
    if not isinstance(until, datetime) or retention.get('Mode') != 'COMPLIANCE':
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    required = required_until or datetime.now(timezone.utc)
    if required.tzinfo is None:
        required = required.replace(tzinfo=timezone.utc)
    return until >= required


async def export_new(retain_days: int = 365) -> dict:
    from app.services.audit_integrity import inspect_chain, inspect_rows
    if not 1 <= retain_days <= 3650:
        raise ValueError('Retention must be between 1 and 3650 days')
    report = await inspect_chain()
    if not report['fully_verified'] and report['status'] != 'empty':
        raise AuditExportBlocked('Audit records are damaged or not fully verifiable; preserve them as incident evidence instead')
    evidence = await verify_external_evidence()
    if evidence['status'] not in ('no_archives', 'verified'):
        raise AuditExportBlocked('Existing external evidence is missing, unavailable, incomplete or does not match; archive verification is required')
    # The cursor comes from verified storage evidence, never a mutable DB marker.
    after = evidence.get('last_archived_row_id') or 0
    rows = await _fetch_rows_after(after)
    if not rows:
        return {"rows": 0, "object_key": None, "last_audit_id": after}
    batch = inspect_rows(rows, previous_hash=rows[0].prev_hash)
    if not batch['fully_verified']:
        raise AuditExportBlocked('Audit export batch failed verification')
    last_id = rows[-1].id
    key = f"audit/worm/{after + 1}-{last_id}-{utc_now():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex}.jsonl"
    retain_until = utc_now().replace(microsecond=0) + timedelta(days=retain_days)
    body = _serialize_jsonl(rows).encode()
    object_key = await _put_worm_object(key, body, retain_until)
    await _record_marker(last_id, object_key, len(rows), retain_until)
    return {"rows": len(rows), "object_key": object_key, "last_audit_id": last_id,
            "retain_until": retain_until.isoformat()}


_MAX_OBJECTS = 1000
_MAX_BYTES = 64 * 1024 * 1024


def _read_external_archives():
    """Discover storage objects independently of mutable DB export markers."""
    client, bucket = _s3_client()
    listing = client.list_object_versions(Bucket=bucket, Prefix='audit/worm/', MaxKeys=min(1000, _MAX_OBJECTS + 1))
    objects = listing.get('Versions', [])
    partial = bool(listing.get('IsTruncated')) or len(objects) > _MAX_OBJECTS
    archives = []
    total_bytes = 0
    deadline = time.monotonic() + 20
    for item in objects[:_MAX_OBJECTS]:
        if time.monotonic() > deadline or total_bytes + item['Size'] > _MAX_BYTES:
            partial = True
            break
        key = item['Key']
        version = item.get('VersionId')
        if not version:
            raise RuntimeError('Versioned immutable archive storage is required')
        retention = client.get_object_retention(Bucket=bucket, Key=key, VersionId=version).get('Retention', {})
        locked = _retention_valid(retention)
        obj = client.get_object(Bucket=bucket, Key=key, VersionId=version)
        try:
            body = obj['Body'].read(_MAX_BYTES - total_bytes + 1)
        finally:
            obj['Body'].close()
        total_bytes += len(body)
        if total_bytes > _MAX_BYTES:
            partial = True
            break
        records = [json.loads(line) for line in body.decode().splitlines() if line.strip()]
        archives.append({'key': key, 'version_id': version, 'locked': locked, 'records': records,
                         'sha256': hashlib.sha256(body).hexdigest()})
    return archives, partial


async def verify_external_evidence():
    if not (os.environ.get('S3_ENDPOINT') or os.environ.get('OSS_ENDPOINT')) or not os.environ.get('S3_ACCESS_KEY'):
        return {'status': 'not_configured', 'verified': False}
    try:
        archives, partial = await asyncio.to_thread(_read_external_archives)
        if not archives:
            return {'status': 'partial' if partial else 'no_archives', 'verified': False}
        from sqlalchemy import select
        from app.core.database import get_db_context
        from app.models.audit import AuditLog
        async with get_db_context() as session:
            rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
        current = {r.id: json.loads(_serialize_jsonl([r])) for r in rows}
        return compare_archives(archives, current, partial=partial)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('External audit evidence check failed')
        code = getattr(exc, 'response', {}).get('Error', {}).get('Code')
        status = 'bucket_missing' if code == 'NoSuchBucket' else 'permission_denied' if code == 'AccessDenied' else 'unavailable'
        return {'status': status, 'verified': False}


def compare_archives(archives, current, *, partial=False):
    from app.services.audit_integrity import inspect_rows
    mismatches = set()
    covered = set()
    unprotected = 0
    incomplete = 0
    objects = []
    required = set(_FIELDS) | {'timestamp'}
    for archive in archives:
        records = archive['records']
        if not archive['locked']:
            unprotected += 1
        if not records or any(not isinstance(r, dict) or not required.issubset(r) for r in records):
            incomplete += 1
            continue
        ids = [r['id'] for r in records]
        if ids != sorted(set(ids)):
            incomplete += 1
            continue
        report = inspect_rows([SimpleNamespace(**r) for r in records], previous_hash=records[0]['prev_hash'])
        if not report['fully_verified']:
            incomplete += 1
        for record in records:
            rid = record['id']
            covered.add(rid)
            if current.get(rid) != record:
                mismatches.add(rid)
        objects.append({'object_key': archive['key'], 'sha256': archive['sha256'], 'version_id': archive.get('version_id'),
                        'first_row_id': ids[0], 'last_row_id': ids[-1],
                        'retention_locked': archive['locked']})
    last = max(covered) if covered else None
    coverage_gap = last is not None and any(rid <= last and rid not in covered for rid in current)
    status = ('mismatch' if mismatches else 'unprotected' if unprotected else
              'partial' if partial or incomplete or coverage_gap else 'verified')
    return {'status': status, 'verified': status == 'verified',
            'archived_rows': len(covered), 'mismatch_count': len(mismatches),
            'mismatch_row_ids': sorted(mismatches)[:100], 'objects_checked': len(archives),
            'unprotected_objects': unprotected, 'incomplete_objects': incomplete,
            'last_archived_row_id': last,
            'unarchived_rows': sum(rid not in covered for rid in current),
            'objects': objects,
            'scope': 'discovered_archives', 'independent_storage_required': True}
