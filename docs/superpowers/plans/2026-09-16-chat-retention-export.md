# Chat WORM Export and Retention (Round 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror whole conversations to write-once object storage, then dispose of the ones whose retention period has passed — without the disposal destroying the evidence.

**Architecture:** One export object per conversation, containing every message with its chain fields, verified before upload and written with S3 Object Lock. A conversation becomes purgeable only when an export holds all of it; purging deletes every message, keeps the `conversations` row marked archived, and records the deletion in the global audit chain.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, boto3 1.43, pytest/pytest-asyncio, React 18 + TypeScript + vitest.

**Spec:** `docs/superpowers/specs/2026-09-16-chat-retention-export-design.md`

## Global Constraints

- Migration revision id must be **≤32 characters** — `alembic_version.version_num` is `varchar(32)`. This plan uses `045_conversation_retention` (26 chars), revising `044_conversation_search`.
- **The safety ordering is the point of this round:** purge requires a complete export, so a deployment that cannot archive cannot delete. Tests assert this rather than mocking S3 everywhere and letting it pass unnoticed (spec §6).
- **Never export a conversation whose chain does not verify** (D2). Writing a known-corrupt chain into immutable storage makes the corruption permanent and gives it the appearance of evidence.
- **Purge deletes every message of a conversation or none** (D3). Partial deletion leaves a dangling `prev_hash` and makes retention indistinguishable from tampering.
- `older_than_days` and `retain_days` are **call parameters, stored nowhere** (D8). This repo has shipped six settings nothing read; a retention period that silently stops applying is worse than one that must be typed.
- Export and purge require `Permission.AUDIT_READ` (D9) — the permission `Role.AUDITOR` holds.
- The purge audit row is written **after** the delete commits (spec §5), so a crash leaves a visible inconsistency rather than an audit row claiming a deletion that did not happen.
- Tests run against a real PostgreSQL. `make check` tears the test services down on exit; if pytest reports `Connect call failed … 55432`, run `make test-env-up` and `alembic upgrade head` again.
- S3 is mocked by patching the module's own helpers, as `tests/test_audit_worm.py` does with `patch.object(aw, "_put_worm_object", AsyncMock(...))` — never by pointing boto3 at a real endpoint.
- Commit **only** the files each step names. The tree carries unrelated user WIP (`webui/src/index.css`); never `git add -A` or `git add .`.
- Never pipe pytest into `tail`/`head` before committing — the pipe masks the exit code.

---

### Task 1: The export record

**Files:**
- Create: `app/models/conversation_export.py`
- Create: `alembic/versions/045_conversation_retention.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/conversation.py`
- Test: `tests/test_conversation_retention_schema.py`

**Interfaces:**
- Consumes: `conversation_messages` and `conversations` (Rounds 1–2).
- Produces:
  - `app.models.conversation_export.ConversationExport` — `id`, `conversation_id`, `object_key`, `rows`, `head_seq`, `head_hash`, `retain_until`, `exported_at`
  - `Conversation.purged_at: datetime | None`, `Conversation.export_key: str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_retention_schema.py`:

```python
"""The record that makes a purge accountable.

A purged conversation keeps its row, naming the object that holds what was
deleted. Without that, the chain anchors written in Round 1 would point at a
conversation nothing can resolve, and a person's history would silently shrink
rather than show as archived.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.user import User


@pytest.fixture
async def conv():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"ret_{suffix}", email=f"ret_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        row = Conversation(user_id=user.id, title="retained")
        db.add(row)
        await db.commit()
        ids = (row.id, user.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


@pytest.mark.asyncio
async def test_an_export_can_be_recorded(conv):
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        db.add(ConversationExport(
            conversation_id=conv_id, object_key="conversations/worm/1-2-x.jsonl",
            rows=3, head_seq=2, head_hash="a" * 64,
            retain_until=datetime(2030, 1, 1), exported_at=datetime(2026, 9, 16)))
        await db.commit()

        stored = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == conv_id))).scalar_one()
    assert stored.head_seq == 2
    assert stored.rows == 3
    assert stored.head_hash == "a" * 64


@pytest.mark.asyncio
async def test_a_conversation_can_be_marked_purged(conv):
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        row = await db.get(Conversation, conv_id)
        row.purged_at = datetime(2026, 9, 16)
        row.export_key = "conversations/worm/1-2-x.jsonl"
        await db.commit()

        row = await db.get(Conversation, conv_id)
        await db.refresh(row)
    assert row.purged_at is not None
    assert row.export_key.endswith(".jsonl")


@pytest.mark.asyncio
async def test_a_fresh_conversation_is_not_marked_purged(conv):
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        row = await db.get(Conversation, conv_id)
    assert row.purged_at is None
    assert row.export_key is None


@pytest.mark.asyncio
async def test_several_exports_of_one_conversation_coexist(conv):
    """A conversation is re-exported as it grows; the highest head_seq is
    current, and the older rows name objects that still exist in WORM storage
    and cannot be withdrawn."""
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        for head in (2, 9):
            db.add(ConversationExport(
                conversation_id=conv_id, object_key=f"conversations/worm/{head}.jsonl",
                rows=head + 1, head_seq=head, head_hash=str(head) * 64,
                retain_until=None, exported_at=datetime(2026, 9, 16)))
        await db.commit()

        rows = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == conv_id)
            .order_by(ConversationExport.head_seq))).scalars().all()
    assert [r.head_seq for r in rows] == [2, 9]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/jc/Documents/Claude/Projects/cyber-agent/cyberguard
python -m pytest tests/test_conversation_retention_schema.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.models.conversation_export'`.

- [ ] **Step 3: Write the model**

Create `app/models/conversation_export.py`:

```python
"""A conversation mirrored to write-once storage.

One row per export. A conversation is re-exported as it grows, so several rows
may name the same conversation; the one with the highest ``head_seq`` is
current, and the older rows are kept because each names an object that still
exists in WORM storage and cannot be withdrawn.

Purging a conversation requires a row here whose ``head_seq`` equals the
conversation's last message — "exported at some point" is not enough, or a
conversation exported at seq 40 and since grown to seq 90 would lose fifty
messages that exist in no object.
"""
from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String,
)

from app.core.database import Base
from app.core.time import utc_now


class ConversationExport(Base):
    __tablename__ = "conversation_exports"
    __table_args__ = (
        Index("ix_conv_exports_conv", "conversation_id", "head_seq"),
    )

    id = Column(Integer, primary_key=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String(300), nullable=False)
    rows = Column(Integer, nullable=False)
    head_seq = Column(Integer, nullable=False)
    head_hash = Column(String(64), nullable=False)
    retain_until = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, nullable=False, default=utc_now)
```

In `app/models/__init__.py`, add the import beside the existing
`ConversationMessage` import and add `"ConversationExport"` to `__all__`:

```python
from app.models.conversation_export import ConversationExport
```

In `app/models/conversation.py`, add two columns to `Conversation`, immediately
after `last_anchored_seq`:

```python
    # Set when retention disposed of this conversation's messages. The row
    # survives so the chain anchors still resolve and the person sees an
    # archived conversation rather than a shrinking history.
    purged_at = Column(DateTime, nullable=True, default=None)
    export_key = Column(String(300), nullable=True, default=None)
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/045_conversation_retention.py`:

```python
"""Record a conversation's WORM export, and that it was purged.

Retention disposes of messages; it must not dispose of the account of them.
The conversations row survives a purge carrying purged_at and export_key, so
the chain anchors written in Round 1 still name something that resolves.

Revision ID: 045_conversation_retention  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 044_conversation_search
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "045_conversation_retention"
down_revision: Union[str, None] = "044_conversation_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_exports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=300), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("head_seq", sa.Integer(), nullable=False),
        sa.Column("head_hash", sa.String(length=64), nullable=False),
        sa.Column("retain_until", sa.DateTime(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conv_exports_conv", "conversation_exports",
                    ["conversation_id", "head_seq"])

    op.add_column("conversations", sa.Column("purged_at", sa.DateTime(), nullable=True))
    op.add_column("conversations",
                  sa.Column("export_key", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "export_key")
    op.drop_column("conversations", "purged_at")
    op.drop_index("ix_conv_exports_conv", table_name="conversation_exports")
    op.drop_table("conversation_exports")
```

- [ ] **Step 5: Apply it and run the tests**

```bash
make test-env-up
DATABASE_URL="postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test" \
REDIS_URL="redis://:cyberguard-test-only@localhost:56379/0" REDIS_PASSWORD=cyberguard-test-only \
ENCRYPTION_KEY=1111111111111111111111111111111111111111111111111111111111111111 \
SECRET_KEY=2222222222222222222222222222222222222222222222222222222222222222 \
ENVIRONMENT=testing AUTO_APPROVE=false PYTHONPATH="packages:$PWD" \
  .venv/bin/alembic -c alembic.ini upgrade head
python -m pytest tests/test_conversation_retention_schema.py tests/test_alembic_startup.py -q
```

Expected: migration applies; all pass.

- [ ] **Step 6: Commit**

```bash
git add app/models/conversation_export.py app/models/conversation.py \
        app/models/__init__.py alembic/versions/045_conversation_retention.py \
        tests/test_conversation_retention_schema.py
git commit -m "$(cat <<'EOF'
feat: record a conversation's WORM export and its purge

Retention disposes of messages; it must not dispose of the account of them.
The conversations row survives a purge carrying purged_at and export_key, so
Round 1's chain anchors still name something that resolves.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Export a conversation to WORM storage

**Files:**
- Create: `app/services/conversation_export.py`
- Test: `tests/test_conversation_export.py`

**Interfaces:**
- Consumes: `ConversationExport` (Task 1); `verify_conversation_chain` from `app.services.conversation_chain`; `fetch_messages` from `app.services.conversation_messages`.
- Produces, in `app.services.conversation_export`:
  - `serialize_conversation(conv, messages) -> str` — JSONL
  - `async export_conversation(session, conversation_id: int, retain_days: int) -> dict`
  - `async export_eligible(session, older_than_days: int, retain_days: int) -> dict`
  - `async _put_worm_object(key: str, data: bytes, retain_until: datetime) -> str` — the seam tests patch

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_export.py`:

```python
"""Mirroring a conversation to write-once storage.

The object has to be verifiable on its own: a reader with nothing but the file
should be able to recompute the chain and compare its head against the
`conversation.chain_anchor` row in the exported audit log. That is why the
export carries every field the hash covers, and why a conversation whose chain
does not verify is never written — putting a known-corrupt chain into immutable
storage makes the corruption permanent and gives it the look of evidence.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services import conversation_export as ce
from app.services.conversation_chain import verify_conversation_chain
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def world():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"exp_{suffix}", email=f"exp_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        full = Conversation(user_id=user.id, title="Port scan triage")
        empty = Conversation(user_id=user.id, title="Nothing said")
        db.add_all([full, empty])
        await db.commit()

        await append_messages_locked(db, full.id, [
            {"role": "user", "content": "扫描主机的开放端口"},
            {"role": "assistant", "content": "three open ports"},
        ])
        await db.commit()
        ids = dict(user=user.id, full=full.id, empty=empty.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id.in_([ids["full"], ids["empty"]])))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_([ids["full"], ids["empty"]])))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids["user"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.commit()


async def _export(conversation_id, **kw):
    """Export with the upload mocked, returning (summary, uploaded_body)."""
    captured = {}

    async def fake_put(key, data, retain_until):
        captured["key"] = key
        captured["body"] = data.decode()
        return key

    with patch.object(ce, "_put_worm_object", AsyncMock(side_effect=fake_put)):
        async with AsyncSessionLocal() as db:
            summary = await ce.export_conversation(
                db, conversation_id, retain_days=kw.get("retain_days", 365))
            await db.commit()
    return summary, captured


# --- the object ---

@pytest.mark.asyncio
async def test_every_message_is_exported_in_order(world):
    summary, captured = await _export(world["full"])
    lines = [json.loads(line) for line in captured["body"].splitlines()]
    messages = [line for line in lines if line["type"] == "message"]

    assert summary["rows"] == 2
    assert [m["seq"] for m in messages] == [0, 1]
    assert messages[0]["content"] == "扫描主机的开放端口"


@pytest.mark.asyncio
async def test_the_object_carries_the_conversation_itself(world):
    _, captured = await _export(world["full"])
    header = json.loads(captured["body"].splitlines()[0])
    assert header["type"] == "conversation"
    assert header["id"] == world["full"]
    assert header["title"] == "Port scan triage"


@pytest.mark.asyncio
async def test_the_chain_can_be_recomputed_from_the_object_alone(world):
    """The property that makes an export evidence rather than a copy."""
    _, captured = await _export(world["full"])
    rebuilt = [
        SimpleNamespace(**{k: v for k, v in json.loads(line).items() if k != "type"})
        for line in captured["body"].splitlines()
        if json.loads(line)["type"] == "message"
    ]
    # conversation_id is on the header line, not each message; created_at is
    # already the ISO string the hash was computed over, and
    # conversation_chain._iso passes a string through unchanged.
    for row in rebuilt:
        row.conversation_id = world["full"]
    assert verify_conversation_chain(rebuilt) is None


@pytest.mark.asyncio
async def test_the_recorded_head_matches_the_conversations_last_message(world):
    summary, _ = await _export(world["full"])
    async with AsyncSessionLocal() as db:
        head = (await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == world["full"])
            .order_by(ConversationMessage.seq.desc()).limit(1))).scalar_one()
    assert summary["head_seq"] == head.seq
    assert summary["head_hash"] == head.entry_hash


@pytest.mark.asyncio
async def test_the_export_is_recorded(world):
    summary, _ = await _export(world["full"])
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == world["full"]))).scalar_one()
    assert row.object_key == summary["object_key"]
    assert row.rows == 2 and row.head_seq == 1


# --- refusals ---

@pytest.mark.asyncio
async def test_an_empty_conversation_is_skipped(world):
    summary, captured = await _export(world["empty"])
    assert summary["skipped"] == "empty"
    assert "body" not in captured, "nothing should have been uploaded"


@pytest.mark.asyncio
async def test_a_broken_chain_is_reported_and_never_uploaded(world):
    """Writing a known-corrupt chain into immutable storage would make the
    corruption permanent and give it the appearance of evidence."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE conversation_messages SET content = 'tampered' "
            "WHERE conversation_id = :cid AND seq = 0"), {"cid": world["full"]})
        await db.commit()

    summary, captured = await _export(world["full"])
    assert summary["skipped"].startswith("chain-broken")
    assert "body" not in captured, "a corrupt conversation must not be uploaded"

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == world["full"]))).scalars().all()
    assert rows == [], "no export may be recorded for a corrupt conversation"


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_the_others(world):
    """export_eligible processes a batch; a single bad conversation must not
    cost the rest their archive."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE conversation_messages SET content = 'tampered' "
            "WHERE conversation_id = :cid AND seq = 0"), {"cid": world["full"]})
        await db.commit()

    async def fake_put(key, data, retain_until):
        return key

    with patch.object(ce, "_put_worm_object", AsyncMock(side_effect=fake_put)):
        async with AsyncSessionLocal() as db:
            summary = await ce.export_eligible(db, older_than_days=0, retain_days=365)
            await db.commit()

    reported = {s["conversation_id"] for s in summary["skipped"]}
    assert world["full"] in reported
    assert world["empty"] in reported


# --- the operability constraint ---

@pytest.mark.asyncio
async def test_export_fails_loudly_when_s3_is_unconfigured(world, monkeypatch):
    """Every deployment here is in this state. The failure must name what is
    missing, because purge silently finding nothing eligible is the
    consequence."""
    for var in ("S3_ENDPOINT", "OSS_ENDPOINT", "S3_ACCESS_KEY"):
        monkeypatch.delenv(var, raising=False)

    async with AsyncSessionLocal() as db:
        with pytest.raises(RuntimeError) as exc:
            await ce.export_conversation(db, world["full"], retain_days=365)
    assert "S3_ENDPOINT" in str(exc.value)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_export.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.conversation_export'`.

- [ ] **Step 3: Write the service**

Create `app/services/conversation_export.py`:

```python
"""Mirror a whole conversation to write-once object storage.

One object per conversation, not an incremental export keyed on message id.
The chain is per conversation and so is the anchor in the global audit log, so
a conversation is the unit of evidence: an object holding fragments of many
conversations contains no complete chain and can be verified against nothing.

The object carries every field ``entry_hash`` covers, so a reader with nothing
but the file can recompute the chain and compare its head against the
``conversation.chain_anchor`` row in the exported audit log. The two exports
verify each other.

S3 configuration is reused from ``app.services.audit_worm``.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage
from app.services.conversation_chain import verify_conversation_chain

# Everything the chain hashes, so the object can be re-verified on its own.
_MESSAGE_FIELDS = ("seq", "role", "content", "created_at", "run_id", "turn_id",
                   "backfilled", "prev_hash", "entry_hash")


def serialize_conversation(conv: Conversation,
                           messages: List[ConversationMessage]) -> str:
    """JSONL: one header line for the conversation, then one line per message."""
    lines = [json.dumps({
        "type": "conversation",
        "id": conv.id,
        "user_id": conv.user_id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }, sort_keys=True, ensure_ascii=False)]

    for message in messages:
        record: Dict[str, Any] = {"type": "message"}
        for field in _MESSAGE_FIELDS:
            value = getattr(message, field, None)
            record[field] = value.isoformat() if isinstance(value, datetime) else value
        lines.append(json.dumps(record, sort_keys=True, ensure_ascii=False))

    return "\n".join(lines) + "\n"


def _s3_client():
    """Same configuration as the audit WORM export, deliberately."""
    import boto3

    endpoint = os.environ.get("S3_ENDPOINT", os.environ.get("OSS_ENDPOINT", ""))
    access = os.environ.get("S3_ACCESS_KEY", "")
    secret = os.environ.get("S3_SECRET_KEY", "")
    region = os.environ.get("S3_REGION", "us-east-1")
    if not endpoint or not access:
        raise RuntimeError(
            "S3/OSS not configured: set S3_ENDPOINT and S3_ACCESS_KEY. "
            "Nothing can be purged until conversations can be archived.")
    bucket = os.environ.get("CONVERSATION_WORM_BUCKET", "cyberguard-chat-worm")
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


async def export_conversation(
    session: AsyncSession, conversation_id: int, retain_days: int,
) -> Dict[str, Any]:
    """Archive one conversation. Returns what happened, rather than raising.

    Re-export is not deduplicated: if the head has not moved, a second call
    writes a second identical object. Suppressing that would mean trusting the
    marker table to decide whether evidence exists, and the marker table is
    mutable while the objects are not.
    """
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        return {"conversation_id": conversation_id, "skipped": "missing"}

    messages = list((await session.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.seq)
    )).scalars().all())

    if not messages:
        # An empty object would assert the conversation was empty at a moment
        # nothing recorded.
        return {"conversation_id": conversation_id, "skipped": "empty"}

    broken = verify_conversation_chain(messages)
    if broken is not None:
        return {"conversation_id": conversation_id,
                "skipped": f"chain-broken: {broken}"}

    head = messages[-1]
    retain_until = utc_now() + timedelta(days=retain_days)
    key = (f"conversations/worm/{conversation_id}-{head.seq}-"
           f"{utc_now():%Y%m%dT%H%M%SZ}.jsonl")

    object_key = await _put_worm_object(
        key, serialize_conversation(conv, messages).encode(), retain_until)

    session.add(ConversationExport(
        conversation_id=conversation_id, object_key=object_key,
        rows=len(messages), head_seq=head.seq, head_hash=head.entry_hash,
        retain_until=retain_until, exported_at=utc_now()))

    return {"conversation_id": conversation_id, "object_key": object_key,
            "rows": len(messages), "head_seq": head.seq,
            "head_hash": head.entry_hash}


async def export_eligible(
    session: AsyncSession, older_than_days: int, retain_days: int,
) -> Dict[str, Any]:
    """Archive every conversation last updated before the cutoff.

    One conversation's failure is recorded and the rest proceed: a single
    corrupt chain must not cost every other conversation its archive.
    """
    cutoff = utc_now() - timedelta(days=older_than_days)
    ids = list((await session.execute(
        select(Conversation.id)
        .where(Conversation.updated_at < cutoff,
               Conversation.purged_at.is_(None))
        .order_by(Conversation.id)
    )).scalars().all())

    exported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for conversation_id in ids:
        result = await export_conversation(session, conversation_id, retain_days)
        (skipped if "skipped" in result else exported).append(result)

    return {"exported": exported, "skipped": skipped}
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_conversation_export.py -q
```

Expected: all pass.

If `test_the_chain_can_be_recomputed_from_the_object_alone` fails on
`created_at`, check that `verify_conversation_chain` receives the same ISO
string the hash was computed over — `conversation_chain._iso` renders a
`datetime` with `.isoformat()`, and the exported JSON already holds that
string, so a `SimpleNamespace` carrying the string hashes identically. Do not
"fix" this by changing the hash function.

- [ ] **Step 5: Commit**

```bash
git add app/services/conversation_export.py tests/test_conversation_export.py
git commit -m "$(cat <<'EOF'
feat: mirror whole conversations to write-once storage

One object per conversation, not an incremental export keyed on message id:
the chain and the anchor are both per conversation, so an object holding
fragments of many conversations can be verified against nothing.

The chain is verified before the upload. Writing a known-corrupt chain into
immutable storage would make the corruption permanent and give it the
appearance of evidence.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Purge what has been archived

**Files:**
- Create: `app/services/conversation_purge.py`
- Test: `tests/test_conversation_purge.py`

**Interfaces:**
- Consumes: `ConversationExport` (Task 1); `record_action` from `app.core.audit`.
- Produces: `async purge_eligible(session, older_than_days: int, confirm: bool = False) -> dict` returning `{"dry_run": bool, "conversations": [{"conversation_id", "messages", "object_key"}], "messages_deleted": int}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_purge.py`:

```python
"""Disposing of messages without disposing of the account of them.

The safety property is an ordering: a conversation is purgeable only when an
export object holds every one of its messages. A deployment that cannot
archive therefore cannot delete — which is the state of every deployment here,
since S3 is unconfigured.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_messages import append_messages_locked
from app.services.conversation_purge import purge_eligible


@pytest.fixture
async def world():
    """One old, fully exported conversation and three that must survive."""
    suffix = uuid.uuid4().hex[:8]
    long_ago = utc_now() - timedelta(days=400)
    async with AsyncSessionLocal() as db:
        user = User(username=f"pur_{suffix}", email=f"pur_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()

        made = {}
        for key in ("ready", "unexported", "stale_export", "recent"):
            conv = Conversation(user_id=user.id, title=key)
            db.add(conv)
            await db.flush()
            made[key] = conv.id
        await db.commit()

        for key in made:
            await append_messages_locked(db, made[key], [
                {"role": "user", "content": f"{key} one"},
                {"role": "assistant", "content": f"{key} two"},
            ])
        await db.commit()

        # A complete export for "ready"; a stale one for "stale_export".
        db.add(ConversationExport(
            conversation_id=made["ready"], object_key="worm/ready.jsonl",
            rows=2, head_seq=1, head_hash="r" * 64, exported_at=utc_now()))
        db.add(ConversationExport(
            conversation_id=made["stale_export"], object_key="worm/stale.jsonl",
            rows=1, head_seq=0, head_hash="s" * 64, exported_at=utc_now()))
        await db.commit()

        # Age everything except "recent".
        for key in ("ready", "unexported", "stale_export"):
            conv = await db.get(Conversation, made[key])
            conv.updated_at = long_ago
        await db.commit()

        made["user"] = user.id
    yield made
    async with AsyncSessionLocal() as db:
        ids = [v for k, v in made.items() if k != "user"]
        await db.execute(AuditLog.__table__.delete().where(
            AuditLog.user_id == made["user"]))
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id.in_(ids)))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_(ids)))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == made["user"]))
        await db.execute(User.__table__.delete().where(User.id == made["user"]))
        await db.commit()


async def _purge(confirm):
    async with AsyncSessionLocal() as db:
        summary = await purge_eligible(db, older_than_days=365, confirm=confirm)
        await db.commit()
    return summary


def _ids(summary):
    return {c["conversation_id"] for c in summary["conversations"]}


# --- eligibility ---

@pytest.mark.asyncio
async def test_an_old_fully_exported_conversation_is_eligible(world):
    assert world["ready"] in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_an_unexported_conversation_is_never_eligible(world):
    """The safety property: nothing is deleted that was not first archived."""
    assert world["unexported"] not in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_a_partially_exported_conversation_is_not_eligible(world):
    """Exported at seq 0 but now at seq 1 — purging would lose a message that
    exists in no object."""
    assert world["stale_export"] not in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_a_recently_updated_conversation_is_not_eligible(world):
    assert world["recent"] not in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_an_already_purged_conversation_is_not_offered_again(world):
    await _purge(confirm=True)
    assert _ids(await _purge(confirm=False)) == set()


# --- the dry run ---

@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing(world):
    summary = await _purge(confirm=False)
    assert summary["dry_run"] is True
    assert summary["messages_deleted"] == 0

    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == world["ready"]))).scalars().all()
        conv = await db.get(Conversation, world["ready"])
    assert len(remaining) == 2
    assert conv.purged_at is None


# --- the purge ---

@pytest.mark.asyncio
async def test_confirming_deletes_every_message_of_the_conversation(world):
    summary = await _purge(confirm=True)
    assert summary["dry_run"] is False
    assert summary["messages_deleted"] == 2

    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == world["ready"]))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_the_conversation_survives_as_an_archived_record(world):
    await _purge(confirm=True)
    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, world["ready"])
        await db.refresh(conv)
    assert conv is not None, "the row must survive so the chain anchors resolve"
    assert conv.purged_at is not None
    assert conv.export_key == "worm/ready.jsonl"
    assert conv.title == "ready", "the person should still see what it was"


@pytest.mark.asyncio
async def test_untouched_conversations_keep_their_messages(world):
    await _purge(confirm=True)
    async with AsyncSessionLocal() as db:
        for key in ("unexported", "stale_export", "recent"):
            rows = (await db.execute(select(ConversationMessage).where(
                ConversationMessage.conversation_id == world[key]))).scalars().all()
            assert len(rows) == 2, f"{key} lost messages it should have kept"


@pytest.mark.asyncio
async def test_the_deletion_is_recorded_in_the_global_audit_chain(world):
    await _purge(confirm=True)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["user"],
            AuditLog.action == "conversation.purged"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action_category == "remediate"
    assert rows[0].entry_hash and rows[0].prev_hash


# --- the operability constraint ---

@pytest.mark.asyncio
async def test_nothing_is_eligible_when_nothing_could_be_exported(world):
    """With S3 unconfigured no export row is ever written, so this is what a
    real deployment here sees: purge finds nothing, however old the data."""
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id.in_(
                [world["ready"], world["stale_export"]])))
        await db.commit()

    assert _ids(await _purge(confirm=False)) == set()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_purge.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.conversation_purge'`.

- [ ] **Step 3: Write the service**

Create `app/services/conversation_purge.py`:

```python
"""Dispose of conversations whose retention period has passed.

The safety property of this module is an ordering, not a check: a conversation
is purgeable only when an export object holds *every* one of its messages. A
deployment that cannot archive therefore cannot delete.

Every message of a conversation goes, or none. Deleting the older half would
leave the oldest survivor's ``prev_hash`` pointing at a row that no longer
exists, and ``verify_conversation_chain`` could no longer tell retention apart
from tampering.

The ``conversations`` row survives, carrying ``purged_at`` and ``export_key``.
Round 1's chain anchors name that conversation in the global audit log, and
they must continue to resolve.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage

logger = logging.getLogger(__name__)

PURGE_ACTION = "conversation.purged"


async def _eligible(session: AsyncSession, older_than_days: int) -> List[Dict[str, Any]]:
    cutoff = utc_now() - timedelta(days=older_than_days)

    heads = (
        select(ConversationMessage.conversation_id.label("cid"),
               func.max(ConversationMessage.seq).label("head_seq"),
               func.count(ConversationMessage.id).label("rows"))
        .group_by(ConversationMessage.conversation_id)
        .subquery()
    )
    # A complete export: one whose head_seq reaches the conversation's last
    # message. "Exported at some point" would lose everything written since.
    complete = (
        select(ConversationExport.conversation_id.label("cid"),
               func.max(ConversationExport.head_seq).label("exported_head"))
        .group_by(ConversationExport.conversation_id)
        .subquery()
    )

    rows = (await session.execute(
        select(Conversation.id, Conversation.user_id, heads.c.rows,
               ConversationExport.object_key)
        .join(heads, heads.c.cid == Conversation.id)
        .join(complete, complete.c.cid == Conversation.id)
        .join(ConversationExport,
              (ConversationExport.conversation_id == Conversation.id)
              & (ConversationExport.head_seq == complete.c.exported_head))
        .where(Conversation.updated_at < cutoff,
               Conversation.purged_at.is_(None),
               complete.c.exported_head == heads.c.head_seq)
        .order_by(Conversation.id)
    )).all()

    return [{"conversation_id": r[0], "user_id": r[1], "messages": r[2],
             "object_key": r[3]} for r in rows]


async def purge_eligible(
    session: AsyncSession, older_than_days: int, confirm: bool = False,
) -> Dict[str, Any]:
    """Report, and with ``confirm`` also delete, what retention has released.

    Dry runs by default: this is the one irreversible operation in the product
    and it should not be a typo away.
    """
    candidates = await _eligible(session, older_than_days)
    summary: Dict[str, Any] = {
        "dry_run": not confirm,
        "conversations": [
            {"conversation_id": c["conversation_id"], "messages": c["messages"],
             "object_key": c["object_key"]}
            for c in candidates
        ],
        "messages_deleted": 0,
    }
    if not confirm or not candidates:
        return summary

    from app.core.audit import record_action

    deleted = 0
    for candidate in candidates:
        conversation_id = candidate["conversation_id"]
        await session.execute(delete(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id))
        conv = await session.get(Conversation, conversation_id)
        conv.purged_at = utc_now()
        conv.export_key = candidate["object_key"]
        await session.commit()
        deleted += candidate["messages"]

        # After the commit on purpose: a crash between them leaves a purged
        # conversation with no audit row — a visible inconsistency — rather
        # than an audit row claiming a deletion that did not happen.
        await record_action(
            user_id=candidate["user_id"],
            action=PURGE_ACTION,
            action_category="remediate",
            risk_tier="high",
            rollback_possible=False,
            input_data={"conversation_id": conversation_id,
                        "older_than_days": older_than_days},
            output_data={"messages_deleted": candidate["messages"],
                         "object_key": candidate["object_key"]},
        )

    summary["messages_deleted"] = deleted
    logger.info("[conversation_purge] disposed of %d message(s) across %d "
                "conversation(s)", deleted, len(candidates))
    return summary
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_conversation_purge.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/conversation_purge.py tests/test_conversation_purge.py
git commit -m "$(cat <<'EOF'
feat: dispose of conversations that have been archived

The safety property is an ordering: a conversation is purgeable only when an
export holds every one of its messages, so a deployment that cannot archive
cannot delete.

Every message goes or none — deleting the older half would leave the oldest
survivor's prev_hash pointing at a row that no longer exists, and the verifier
could no longer tell retention from tampering.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: The endpoints, and what an archived conversation looks like

**Files:**
- Modify: `app/routers/conversations.py` — two new routes plus `archived` on the response and a 409 on append
- Test: `tests/test_conversation_retention_api.py`

**Interfaces:**
- Consumes: `export_eligible` (Task 2), `purge_eligible` (Task 3).
- Produces: `POST /conversations/export`, `POST /conversations/purge`; `ConversationResponse.archived: bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_retention_api.py`:

```python
"""What retention looks like from outside.

An archived conversation still appears with its title: "your conversation is
empty" would be a lie, and a history that silently shrinks is worse than one
that says what happened to it.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.routers.conversations import (
    AppendMessageRequest, append_message, list_conversations,
)


@pytest.fixture
async def archived():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"arch_{suffix}", email=f"arch_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="Archived work",
                            purged_at=utc_now(), export_key="worm/a.jsonl")
        live = Conversation(user_id=user.id, title="Still here")
        db.add_all([conv, live])
        await db.commit()
        ids = (conv.id, live.id, user.id, user.username, user.email)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_([ids[0], ids[1]])))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[2]))
        await db.execute(User.__table__.delete().where(User.id == ids[2]))
        await db.commit()


def _user(archived):
    _, _, user_id, username, email = archived
    return AuthenticatedUser(user_id=user_id, username=username,
                             email=email, role="admin")


@pytest.mark.asyncio
async def test_an_archived_conversation_is_still_listed(archived):
    conv_id, *_ = archived
    async with AsyncSessionLocal() as db:
        listed = await list_conversations(db, _user(archived))
    row = next(c for c in listed if c.id == conv_id)
    assert row.archived is True
    assert row.title == "Archived work"
    assert row.message_count == 0


@pytest.mark.asyncio
async def test_a_live_conversation_is_not_marked_archived(archived):
    _, live_id, *_ = archived
    async with AsyncSessionLocal() as db:
        listed = await list_conversations(db, _user(archived))
    assert next(c for c in listed if c.id == live_id).archived is False


@pytest.mark.asyncio
async def test_appending_to_an_archived_conversation_is_refused(archived):
    """Resuming it would start a second chain at seq 0, colliding with the one
    already exported."""
    from fastapi import HTTPException

    conv_id, *_ = archived
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await append_message(
                conv_id, AppendMessageRequest(role="user", content="more"),
                db, _user(archived))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_appending_to_a_live_conversation_still_works(archived):
    _, live_id, *_ = archived
    async with AsyncSessionLocal() as db:
        result = await append_message(
            live_id, AppendMessageRequest(role="user", content="hello"),
            db, _user(archived))
    assert result["message_count"] == 1


def test_the_endpoints_require_the_auditor_permission():
    """Export and purge are the auditor's job — AUDIT_READ is the permission
    Role.AUDITOR holds, and it does not carry the right to change the system."""
    import inspect

    from app.routers.conversations import export_conversations, purge_conversations

    for handler in (export_conversations, purge_conversations):
        assert "AUDIT_READ" in inspect.getsource(handler), handler.__name__


def test_purge_dry_runs_unless_confirmed():
    import inspect

    from app.routers.conversations import purge_conversations

    signature = inspect.signature(purge_conversations)
    assert signature.parameters["confirm"].default is False
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_retention_api.py -q
```

Expected: FAIL — `ConversationResponse` has no `archived`, and the two handlers do not exist.

- [ ] **Step 3: Add `archived` to the response**

In `app/routers/conversations.py`, add to `ConversationResponse` after
`last_message_preview`:

```python
    # True once retention has disposed of the messages. The row survives so the
    # person sees an archived conversation rather than an empty one.
    archived: bool = False
```

and in `list_conversations`, set it where `message_count` is already set:

```python
        payload.archived = conv.purged_at is not None
```

- [ ] **Step 4: Refuse appends to an archived conversation**

In `append_message`, immediately after the `if not conv:` 404 check:

```python
    if conv.purged_at is not None:
        # A second chain starting at seq 0 would collide with the one already
        # exported, and the history it belongs to no longer lives here.
        raise HTTPException(
            status_code=409,
            detail="This conversation has been archived and cannot be continued.")
```

Note that `append_messages_locked` has already inserted the message rows into
the session at this point, so the exception must be raised before `db.commit()`
— it is, since the commit is the next statement. Verify the archived-append
test asserts no message was written by re-reading after the 409 if you change
this ordering.

- [ ] **Step 5: Add the two endpoints**

In `app/routers/conversations.py`, add these **after** `append_message` at the
end of the file. Placement is safe here, unlike Round 2's search route: the
only POST routes on this router are `/conversations` and
`/conversations/{conv_id}/messages`, so there is no `POST /conversations/
{conv_id}` for these literal paths to be swallowed by. Verify that is still
true before adding them:

```bash
grep -n '@router.post' app/routers/conversations.py
```

```python
@router.post("/conversations/export")
async def export_conversations(
    older_than_days: int = 0,
    retain_days: int = 365,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """Mirror conversations to write-once storage.

    older_than_days=0 exports everything; retention disposes of nothing that
    has not been through here first.
    """
    from app.services.conversation_export import export_eligible

    summary = await export_eligible(
        db, older_than_days=older_than_days, retain_days=retain_days)
    await db.commit()
    return summary


@router.post("/conversations/purge")
async def purge_conversations(
    older_than_days: int = 365,
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """Dispose of archived conversations older than the cutoff.

    Dry runs unless `confirm` is true. This is the one irreversible operation
    in the product; it should not be a typo away.
    """
    from app.services.conversation_purge import purge_eligible

    return await purge_eligible(
        db, older_than_days=older_than_days, confirm=confirm)
```

- [ ] **Step 6: Run the tests**

```bash
python -m pytest tests/test_conversation_retention_api.py \
                tests/test_conversation_immutability.py \
                tests/test_conversation_search.py -q
```

Expected: all pass. If `test_conversation_immutability.py` fails because
`ConversationResponse` gained a field, the assertion there checks specific
field *absence* rather than an exact set — read it before changing it.

- [ ] **Step 7: Commit**

```bash
git add app/routers/conversations.py tests/test_conversation_retention_api.py
git commit -m "$(cat <<'EOF'
feat: expose export and purge, and show an archived conversation as archived

An archived conversation keeps its title and reports archived: true. "Your
conversation is empty" would be a lie, and a history that silently shrinks is
worse than one that says what happened to it.

Appending to one is refused with 409: a second chain starting at seq 0 would
collide with the one already exported.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: INV-44, and the archived view

**Files:**
- Modify: `tests/test_invariants_static.py`
- Modify: `docs/delivery/ARCHITECTURE_AND_SECURITY.md`
- Modify: `webui/src/pages/Chat.tsx` — the empty-transcript branch at line 934
- Modify: `webui/src/api/client.ts` — the `Conversation` type
- Modify: `webui/src/i18n/en.json`, `webui/src/i18n/zh.json`
- Test: `webui/src/pages/Chat.archived.test.tsx`

**Interfaces:**
- Consumes: `ConversationResponse.archived` (Task 4).
- Produces: no new exports.

- [ ] **Step 1: Write the failing frontend test**

Create `webui/src/pages/Chat.archived.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import Chat from './Chat'

/**
 * A purged conversation has no messages, but it is not an empty conversation.
 * Showing the ordinary "no messages yet" state would tell the person their
 * history was never there, when in fact it was archived to write-once storage
 * and the row still names the object holding it.
 */
describe('Chat — an archived conversation', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getConversationMessages').mockResolvedValue({ messages: [] } as never)
    vi.spyOn(api, 'getAgents').mockResolvedValue([] as never)
    vi.spyOn(api, 'getProviders').mockResolvedValue([] as never)
  })

  it('says the transcript was archived rather than that it is empty', async () => {
    vi.spyOn(api, 'getConversations').mockResolvedValue([
      { id: 5, title: 'Archived work', archived: true, message_count: 0 },
    ] as never)

    render(<Chat />)

    await waitFor(() => expect(screen.getByText(/archived/i)).toBeTruthy())
  })

  it('still shows the ordinary empty state for a new conversation', async () => {
    vi.spyOn(api, 'getConversations').mockResolvedValue([
      { id: 6, title: 'Brand new', archived: false, message_count: 0 },
    ] as never)

    render(<Chat />)

    await waitFor(() => expect(screen.queryByText(/archived/i)).toBeNull())
  })
})
```

Before writing the implementation, open `webui/src/pages/Chat.tsx` around line
934 and read the existing empty branch and the props `Chat` actually takes. If
`Chat` requires props this test does not pass, supply them; do not change the
component's signature to suit the test.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd webui && npx vitest run src/pages/Chat.archived.test.tsx
```

Expected: FAIL — nothing renders the word "archived".

- [ ] **Step 3: Add the strings and the type**

In `webui/src/i18n/en.json` under `chat`, add:

```json
    "archivedTitle": "This conversation has been archived",
    "archivedBody": "Its messages were exported to write-once storage under the retention policy and removed from the live database. The record of what was said is preserved and can be retrieved by an auditor."
```

In `webui/src/i18n/zh.json` under `chat`:

```json
    "archivedTitle": "此对话已归档",
    "archivedBody": "根据留存策略，其消息已导出到一次写入存储并从在线数据库中移除。所说内容的记录仍被保留，审计员可以取回。"
```

In `webui/src/api/client.ts`, add `archived?: boolean` to the `Conversation`
type beside `message_count`.

- [ ] **Step 4: Render the archived state**

In `webui/src/pages/Chat.tsx`, change the empty-transcript branch at line 934
from `messages.length === 0 ? (` to distinguish the two cases:

```tsx
          ) : messages.length === 0 && activeConv?.archived ? (
            <div style={{
              padding: 32, textAlign: 'center', color: 'var(--text-muted)',
              maxWidth: 520, margin: '0 auto', lineHeight: 1.7,
            }}>
              <div style={{
                fontSize: 14, fontWeight: 600, color: 'var(--text-primary)',
                marginBottom: 10,
              }}>
                {t('chat.archivedTitle')}
              </div>
              <div style={{ fontSize: 13 }}>{t('chat.archivedBody')}</div>
            </div>
          ) : messages.length === 0 ? (
```

`activeConv` is whichever entry of `conversations` has `id === activeConvId`;
if the component does not already compute it, add
`const activeConv = conversations.find(c => c.id === activeConvId)` beside the
other derived values rather than inside the JSX.

- [ ] **Step 5: Run the frontend gates**

```bash
cd webui && npx vitest run
cd webui && npx tsc --noEmit -p tsconfig.app.json && npx tsc --noEmit -p tsconfig.test.json
cd .. && .venv/bin/python scripts/eslint_ratchet.py
```

Expected: all pass, both typecheck targets clean, eslint at baseline.

- [ ] **Step 6: Add the invariant**

Append to `tests/test_invariants_static.py`:

```python
# INV-44 · nothing is deleted that was not first archived

def test_inv44_purge_requires_a_complete_export():
    """INV-44: the eligibility query must compare the exported head against the
    conversation's own head. "Exported at some point" would let a conversation
    lose every message written since its last export."""
    import inspect

    from app.services import conversation_purge

    src = inspect.getsource(conversation_purge)
    assert "exported_head == heads.c.head_seq" in src, (
        "purge no longer requires the export to reach the conversation's head")


def test_inv44_purge_deletes_whole_conversations_only():
    """INV-44: a partial delete would leave a dangling prev_hash, and the
    verifier could no longer tell retention apart from tampering."""
    import inspect

    from app.services.conversation_purge import purge_eligible

    src = inspect.getsource(purge_eligible)
    assert "ConversationMessage.conversation_id == conversation_id" in src
    assert ".seq" not in src.split("delete(ConversationMessage)")[1][:400], (
        "the delete is filtered by seq, so it removes part of a conversation")


def test_inv44_only_the_purge_service_deletes_messages():
    """INV-44: a second deletion site would be messages leaving without an
    export and without an audit row."""
    import pathlib
    import re

    allowed = {"app/services/conversation_purge.py"}
    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r"delete\(ConversationMessage\)")
    offenders = []
    for path in (root / "app").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in allowed:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == [], (
        "INV-44 violated — these delete messages outside the purge service:\n"
        + "\n".join(offenders))


def test_inv44_a_purged_conversation_keeps_its_row():
    """INV-44: the row is what makes the chain anchors still resolve."""
    import inspect

    from app.services.conversation_purge import purge_eligible

    src = inspect.getsource(purge_eligible)
    assert "conv.purged_at" in src and "conv.export_key" in src
    assert "delete(Conversation)" not in src
```

- [ ] **Step 7: Document the invariant**

In `docs/delivery/ARCHITECTURE_AND_SECURITY.md`, after the INV-43 paragraph:

```markdown
INV-44: nothing is deleted that was not first archived. A conversation's
messages may be removed only when an export object in write-once storage holds
every one of them with its chain intact (`app/services/conversation_export.py`),
the `conversations` row survives naming that object, and the deletion is
recorded in the global audit chain as `conversation.purged`
(`app/services/conversation_purge.py`). Purge dry-runs unless confirmed, and a
deployment with no object storage configured finds nothing eligible — it cannot
delete what it cannot archive.
See `docs/superpowers/specs/2026-09-16-chat-retention-export-design.md`.
```

- [ ] **Step 8: Run everything**

```bash
cd /Users/jc/Documents/Claude/Projects/cyber-agent/cyberguard && make check
```

Expected: full Python suite + invariants + frontend gates green.

- [ ] **Step 9: Commit**

```bash
git add tests/test_invariants_static.py docs/delivery/ARCHITECTURE_AND_SECURITY.md \
        webui/src/pages/Chat.tsx webui/src/pages/Chat.archived.test.tsx \
        webui/src/api/client.ts webui/src/i18n/en.json webui/src/i18n/zh.json
git commit -m "$(cat <<'EOF'
feat: enforce INV-44 and show an archived transcript as archived

Nothing is deleted that was not first archived: purge requires an export
reaching the conversation's own head, deletes whole conversations only, and is
the single place messages may be removed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| §1 one object per conversation | 2 |
| §2 D1 per-conversation export | 2 |
| §2 D2 verify before writing | 2 (`test_a_broken_chain_is_reported_and_never_uploaded`) |
| §2 D3 whole conversations only | 3, 5 (INV-44) |
| §2 D4 the row survives | 1, 3, 5 (INV-44) |
| §2 D5 complete export required | 3 (`test_a_partially_exported_conversation_is_not_eligible`), 5 |
| §2 D6 age governs, not deletion state | 3 (`_eligible` filters on `updated_at` only) |
| §2 D7 dry run by default | 3, 4 |
| §2 D8 call parameters, no settings | 3, 4 (both take `older_than_days`) |
| §2 D9 `AUDIT_READ` | 4 |
| §3 schema, §3.1 object format | 1, 2 |
| §4 export | 2 |
| §5 purge, §5.1 the person's view | 3, 4, 5 |
| §6 operability / S3 unconfigured | 2 (`test_export_fails_loudly…`), 3 (`test_nothing_is_eligible…`) |
| §7 testing | 1–5 |
| §8 INV-44 | 5 |
