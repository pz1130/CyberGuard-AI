# Audit WORM Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Standard's Audit Trail control (B4 phase-2) — mirror the hash-chained audit log to write-once-read-many (WORM) object storage with Object Lock, so the immutable record survives even a full database compromise.

**Architecture:** A `audit_worm` service incrementally exports new `audit_logs` rows (since the last export marker) as a JSON-lines object to an S3-compatible bucket, written with `ObjectLockMode=COMPLIANCE` + a retention date. Reuses the project's existing boto3/S3 pattern from `app/routers/backup.py` (same `S3_ENDPOINT`/`S3_ACCESS_KEY`/… env). A small marker table tracks the last exported id and object key. Exposed via `POST /audit/worm-export`; can be scheduled later.

**Tech Stack:** boto3 (S3 Object Lock), SQLAlchemy async, FastAPI, `asyncio.to_thread` for sync boto3, pytest. One small migration.

---

## Dependencies & decisions

- **Depends on** the hash-chained `audit_logs` from Phase-1 of `2026-06-09-agent-governance-controls.md` (the WORM object preserves `entry_hash`/`prev_hash` so off-site copies are independently verifiable).
- **Reuses** the S3 config already in the codebase (`app/routers/backup.py`): `S3_ENDPOINT`/`OSS_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`. The target **bucket must be created with Object Lock enabled** (an account/bucket prerequisite, documented, not done by this code).
- **Retention** default 365 days (`COMPLIANCE` mode — not even the root account can delete before expiry), configurable per call.
- **Incremental & append-only:** each export covers `id > last_exported_id`; objects are keyed by id range + timestamp so they never overwrite. Export is **best-effort additive** — it never mutates the DB rows.
- **Migration head note:** this migration chains on the current head. The number below assumes the safety-envelope plan landed (`029_rollback_registry`); if landing in a different order, set `down_revision` to the actual head at implementation time.

## File Structure

| File | Responsibility |
|------|----------------|
| `app/models/audit_worm.py` (create) | `AuditWormExport` marker table |
| `alembic/versions/030_audit_worm_exports.py` (create) | Migrate the marker table |
| `app/services/audit_worm.py` (create) | Serialize → put_object(Object Lock) → advance marker |
| `app/routers/audit.py` (modify) | `POST /audit/worm-export` |
| `tests/test_audit_worm.py` (create) | Serialization + marker-advance (S3 mocked) |

---

### Task 1: Export marker table

**Files:**
- Create: `app/models/audit_worm.py`, `alembic/versions/030_audit_worm_exports.py`

- [ ] **Step 1: Model**

```python
# app/models/audit_worm.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base


class AuditWormExport(Base):
    __tablename__ = "audit_worm_exports"
    id = Column(Integer, primary_key=True, index=True)
    last_audit_id = Column(Integer, nullable=False)      # highest audit_logs.id in this object
    object_key = Column(String(300), nullable=False)
    rows = Column(Integer, nullable=False)
    retain_until = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

- [ ] **Step 2: Migration `030_audit_worm_exports.py`**

```python
"""audit_worm_exports marker table

Revision ID: 030_audit_worm_exports
Revises: 029_rollback_registry
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "030_audit_worm_exports"
down_revision = "029_rollback_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "audit_worm_exports" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "audit_worm_exports",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("last_audit_id", sa.Integer, nullable=False),
            sa.Column("object_key", sa.String(300), nullable=False),
            sa.Column("rows", sa.Integer, nullable=False),
            sa.Column("retain_until", sa.DateTime, nullable=True),
            sa.Column("exported_at", sa.DateTime, nullable=False),
        )


def downgrade() -> None:
    if "audit_worm_exports" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("audit_worm_exports")
```

- [ ] **Step 3: Migrate + commit**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
git add app/models/audit_worm.py alembic/versions/030_audit_worm_exports.py
git commit -m "feat(audit-worm): export marker table + migration 030"
```

### Task 2: WORM export service

**Files:**
- Create: `app/services/audit_worm.py`
- Test: `tests/test_audit_worm.py`

- [ ] **Step 1: Write the failing tests** (serialization is DB-free; the export path mocks DB + S3)

```python
# tests/test_audit_worm.py
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services import audit_worm as aw


def test_serialize_jsonl_includes_chain_fields():
    rows = [SimpleNamespace(id=1, action="gatekeeper:allow", entry_hash="e1", prev_hash="0"*64,
                            input_hash="i1", output_hash="o1", timestamp=None, agent_name="a",
                            action_category="observe", confidence=None, human_reviewer=None,
                            rollback_possible=None, risk_tier="low", request_id="r1", user_id=1,
                            agent_id=None)]
    text = aw._serialize_jsonl(rows)
    line = json.loads(text.strip())
    assert line["entry_hash"] == "e1" and line["prev_hash"] == "0"*64
    assert line["id"] == 1 and line["action"] == "gatekeeper:allow"


@pytest.mark.asyncio
async def test_export_advances_marker_and_uploads():
    rows = [SimpleNamespace(id=5, action="x", entry_hash="e5", prev_hash="e4",
                            input_hash="i", output_hash="o", timestamp=None, agent_name=None,
                            action_category=None, confidence=None, human_reviewer=None,
                            rollback_possible=None, risk_tier=None, request_id="r", user_id=1, agent_id=None)]
    with patch.object(aw, "_last_exported_id", AsyncMock(return_value=0)), \
         patch.object(aw, "_fetch_rows_after", AsyncMock(return_value=rows)), \
         patch.object(aw, "_put_worm_object", AsyncMock(return_value="audit/worm/1-5.jsonl")), \
         patch.object(aw, "_record_marker", AsyncMock()) as marker:
        summary = await aw.export_new(retain_days=365)
    assert summary["rows"] == 1 and summary["last_audit_id"] == 5
    marker.assert_awaited()


@pytest.mark.asyncio
async def test_export_noop_when_nothing_new():
    with patch.object(aw, "_last_exported_id", AsyncMock(return_value=10)), \
         patch.object(aw, "_fetch_rows_after", AsyncMock(return_value=[])):
        summary = await aw.export_new()
    assert summary["rows"] == 0 and summary.get("object_key") is None
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_audit_worm.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.services.audit_worm`.

- [ ] **Step 3: Implement `app/services/audit_worm.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_audit_worm.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/audit_worm.py tests/test_audit_worm.py
git commit -m "feat(audit-worm): incremental WORM export with S3 Object Lock"
```

### Task 3: Export endpoint

**Files:**
- Modify: `app/routers/audit.py`

- [ ] **Step 1: Add the endpoint** (admin-only; match the file's existing admin dependency, as used by `/audit/verify`)

```python
from app.services.audit_worm import export_new

@router.post("/audit/worm-export", tags=["Audit"])
async def audit_worm_export(retain_days: int = 365, current_user=Depends(get_current_admin_user)):
    return await export_new(retain_days=retain_days)
```

- [ ] **Step 2: Smoke-check + commit**

```bash
.venv/bin/python -c "import app.routers.audit; print('ok')"
git add app/routers/audit.py
git commit -m "feat(audit-worm): POST /audit/worm-export endpoint"
```

**Plan gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

## Self-Review notes (coverage vs the Standard)

- **B4 "WORM or cryptographically signed"** → now both: hash chain (Phase-1) **and** Object-Lock WORM mirror (this plan). Off-site objects carry `entry_hash`/`prev_hash`, so an auditor can verify the chain independently of the DB.
- **Prerequisite (operational, documented):** the target bucket must be created with Object Lock enabled and `AUDIT_WORM_BUCKET` set; `COMPLIANCE` retention means objects cannot be deleted before `retain_until` even by root.
- **Known limitations / follow-ups:** export is **manual/triggered** here — wire it to the existing scheduler (`app/routers/schedule.py`) for a daily cadence as a small follow-up. A `GET /audit/worm/verify` that pulls objects back and re-checks the chain end-to-end would strengthen the audit story but is optional. Object size is unbounded per run; for very large backfills, chunk by id range (the keying scheme already supports it).
- **This is the last open item** in the NDB Standard gap: with this plan, all 13 mandatory controls + the §5 POC requirements are fully planned.
