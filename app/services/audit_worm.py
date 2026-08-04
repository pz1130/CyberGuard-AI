"""Mirror the hash-chained audit log to WORM object storage (NDB Std §Audit Trail).

Incremental, append-only export to an S3 Object-Lock bucket. Reuses the S3 env
config from app/routers/backup.py. Never mutates audit_logs.
"""
from __future__ import annotations
import asyncio
import json
import os
from datetime import datetime, timedelta
from sqlalchemy import select, func

_FIELDS = ("id", "user_id", "agent_id", "agent_name", "action", "action_category",
           "confidence", "human_reviewer", "rollback_possible", "risk_tier",
           "input_hash", "output_hash", "request_id", "prev_hash", "entry_hash")


def _serialize_jsonl(rows) -> str:
    out = []
    for r in rows:
        rec = {f: getattr(r, f, None) for f in _FIELDS}
        rec["timestamp"] = getattr(r, "timestamp", None).isoformat() if getattr(r, "timestamp", None) else None
        out.append(json.dumps(rec, sort_keys=True, default=str))
    return "\n".join(out) + ("\n" if out else "")


async def _last_exported_id() -> int:
    from app.core.database import get_db_context
    from app.models.audit_worm import AuditWormExport
    async with get_db_context() as s:
        return (await s.execute(select(func.coalesce(func.max(AuditWormExport.last_audit_id), 0)))).scalar() or 0


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
                              retain_until=retain_until, exported_at=datetime.utcnow()))
        await s.commit()


def _s3_client():
    import boto3
    endpoint = os.environ.get("S3_ENDPOINT", os.environ.get("OSS_ENDPOINT", ""))
    access = os.environ.get("S3_ACCESS_KEY", "")
    secret = os.environ.get("S3_SECRET_KEY", "")
    region = os.environ.get("S3_REGION", "us-east-1")
    if not endpoint or not access:
        raise RuntimeError("S3/OSS not configured: set S3_ENDPOINT and S3_ACCESS_KEY")
    bucket = os.environ.get("AUDIT_WORM_BUCKET", "cyberguard-audit-worm")
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access,
                        aws_secret_access_key=secret, region_name=region), bucket


async def _put_worm_object(key: str, data: bytes, retain_until: datetime) -> str:
    def _do():
        client, bucket = _s3_client()
        client.put_object(Bucket=bucket, Key=key, Body=data,
                          ObjectLockMode="COMPLIANCE",
                          ObjectLockRetainUntilDate=retain_until)
        return key
    return await asyncio.to_thread(_do)


async def export_new(retain_days: int = 365) -> dict:
    after = await _last_exported_id()
    rows = await _fetch_rows_after(after)
    if not rows:
        return {"rows": 0, "object_key": None, "last_audit_id": after}
    last_id = rows[-1].id
    key = f"audit/worm/{after + 1}-{last_id}-{datetime.utcnow():%Y%m%dT%H%M%SZ}.jsonl"
    retain_until = datetime.utcnow() + timedelta(days=retain_days)
    body = _serialize_jsonl(rows).encode()
    object_key = await _put_worm_object(key, body, retain_until)
    await _record_marker(last_id, object_key, len(rows), retain_until)
    return {"rows": len(rows), "object_key": object_key, "last_audit_id": last_id,
            "retain_until": retain_until.isoformat()}
