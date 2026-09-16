# Chat Message Storage (Round 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move chat history out of the `conversations.messages_json` blob into an append-only, hash-chained `conversation_messages` table, anchored into the global audit chain.

**Architecture:** One row per message, chained per conversation (`prev_hash` → the previous message *in that conversation*), so writers serialise only against the conversation row lock that already exists and never against the global audit advisory lock. A Celery beat task periodically writes each conversation's chain head into `audit_logs`, which is what makes a wholesale conversation deletion detectable.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 (async + sync sessions), Alembic, PostgreSQL, Celery, pytest/pytest-asyncio, React 18 + TypeScript + vitest.

**Spec:** `docs/superpowers/specs/2026-09-16-chat-message-storage-design.md`

## Global Constraints

- Migration revision id must be **≤32 characters** — `alembic_version.version_num` is `varchar(32)`. This plan uses `041_conversation_messages` (26 chars), revising `040_conv_title_no_default`.
- Genesis hash is `"0" * 64`, matching `app.core.audit._GENESIS` and `app.services.run_event_log._GENESIS`.
- **The hash is always computed from the value that gets stored**, never from the caller's input string. `created_at` is normalised to a naive-UTC `datetime` first, then both stored and hashed via `.isoformat()`. Getting this backwards makes every row fail verification.
- `backfilled` is **outside** the hash (spec §3.1). Do not add it to the digest.
- All datetimes stored in this codebase are **naive UTC** (`app/core/time.utc_now`). `tests/test_conversation_update.py` asserts `conv.updated_at.tzinfo is None`; keep that property.
- Tests run against a real PostgreSQL (`make test` brings up a disposable instance and runs `alembic upgrade head` first). Postgres-only SQL (`DISTINCT ON`) is allowed.
- Never pipe pytest into `tail`/`head` before committing — the pipe masks pytest's exit code and lets a red suite be committed. Use `pytest …; rc=$?; if [ $rc -ne 0 ]; then exit 1; fi`.
- `pyproject.toml` sets `asyncio_mode = "auto"`, so async tests and async fixtures need no `@pytest_asyncio.fixture` decorator; `AsyncSessionLocal` is built with `expire_on_commit=False`, so attributes stay readable after `await session.commit()`.
- Commit **only** the files each step names. The working tree carries unrelated user WIP (`webui/src/index.css`, `webui/src/pages/Security.tsx`, `package.json`) that must never be swept into these commits.

---

### Task 1: The chain, as a pure module

No database, no I/O — the same shape as `app/core/audit_diff.py`. Everything later in the plan depends on these two functions agreeing with each other, so they get their own test cycle first.

**Files:**
- Create: `app/services/conversation_chain.py`
- Test: `tests/test_conversation_chain.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `GENESIS: str` — `"0" * 64`
  - `entry_hash(*, conversation_id: int, seq: int, role: str, content: str, created_at: datetime | str, run_id: str | None, turn_id: str | None, prev_hash: str) -> str`
  - `verify_conversation_chain(messages: Sequence[Any]) -> Optional[str]` — `None` when intact, else a string naming the first broken row. Accepts anything with `.conversation_id/.seq/.role/.content/.created_at/.run_id/.turn_id/.prev_hash/.entry_hash`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_chain.py`:

```python
"""The per-conversation hash chain, as arithmetic — no database involved.

The chain is what turns a transcript into evidence, so the hash function and
the verifier have to agree exactly. Testing them against each other here, with
plain objects, means a later failure in a DB test is a storage bug and not a
disagreement about the formula.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.conversation_chain import (
    GENESIS,
    entry_hash,
    verify_conversation_chain,
)

T0 = datetime(2026, 9, 16, 12, 0, 0)


def _row(seq, content, prev_hash, *, conversation_id=7, role="user",
         created_at=T0, run_id=None, turn_id=None, entry=None):
    digest = entry or entry_hash(
        conversation_id=conversation_id, seq=seq, role=role, content=content,
        created_at=created_at, run_id=run_id, turn_id=turn_id, prev_hash=prev_hash,
    )
    return SimpleNamespace(
        conversation_id=conversation_id, seq=seq, role=role, content=content,
        created_at=created_at, run_id=run_id, turn_id=turn_id,
        prev_hash=prev_hash, entry_hash=digest,
    )


def _chain(*contents, conversation_id=7):
    rows, prev = [], GENESIS
    for seq, content in enumerate(contents):
        row = _row(seq, content, prev, conversation_id=conversation_id)
        rows.append(row)
        prev = row.entry_hash
    return rows


def test_genesis_matches_the_other_chains_in_this_codebase():
    from app.core.audit import _GENESIS as audit_genesis
    from app.services.run_event_log import _GENESIS as run_genesis
    assert GENESIS == audit_genesis == run_genesis


def test_an_intact_chain_verifies():
    assert verify_conversation_chain(_chain("hello", "hi", "bye")) is None


def test_an_empty_conversation_verifies():
    assert verify_conversation_chain([]) is None


def test_altering_content_is_detected_and_named():
    rows = _chain("hello", "hi", "bye")
    rows[1].content = "something the AI never said"
    assert verify_conversation_chain(rows) == "content altered at seq 1"


def test_altering_the_role_is_detected():
    """Re-attributing an assistant answer to the user is exactly the forgery
    this chain exists to catch."""
    rows = _chain("hello", "hi")
    rows[1].role = "user"
    assert verify_conversation_chain(rows) == "content altered at seq 1"


def test_altering_the_timestamp_is_detected():
    rows = _chain("hello", "hi")
    rows[1].created_at = datetime(2020, 1, 1)
    assert verify_conversation_chain(rows) == "content altered at seq 1"


def test_a_removed_message_is_detected():
    rows = _chain("a", "b", "c")
    assert verify_conversation_chain([rows[0], rows[2]]) == "seq gap: expected 1, found 2"


def test_a_reordered_pair_is_detected():
    rows = _chain("a", "b")
    assert verify_conversation_chain([rows[1], rows[0]]) == "seq gap: expected 0, found 1"


def test_a_relinked_row_is_detected():
    """Re-chaining a forged row to the right predecessor still fails, because
    the successor's prev_hash no longer matches."""
    rows = _chain("a", "b", "c")
    rows[1] = _row(1, "forged", rows[0].entry_hash)
    assert verify_conversation_chain(rows) == "broken link at seq 2"


def test_the_first_row_must_link_to_genesis():
    rows = _chain("a", "b")
    rows[0].prev_hash = "f" * 64
    assert verify_conversation_chain(rows) == "broken link at seq 0"


def test_two_conversations_do_not_share_a_chain():
    """The same text at the same seq in two conversations must hash
    differently, or a message could be moved between transcripts."""
    a = _chain("identical", conversation_id=1)
    b = _chain("identical", conversation_id=2)
    assert a[0].entry_hash != b[0].entry_hash


def test_a_datetime_and_its_isoformat_hash_alike():
    """The store hashes the datetime it persists; the backfill migration hashes
    the datetime it parsed. They must land on the same digest."""
    common = dict(conversation_id=1, seq=0, role="user", content="x",
                  run_id=None, turn_id=None, prev_hash=GENESIS)
    assert entry_hash(created_at=T0, **common) == entry_hash(
        created_at=T0.isoformat(), **common)


def test_run_and_turn_ids_are_covered():
    common = dict(conversation_id=1, seq=0, role="assistant", content="x",
                  created_at=T0, turn_id=None, prev_hash=GENESIS)
    assert entry_hash(run_id="run-a", **common) != entry_hash(run_id="run-b", **common)


def test_absent_correlation_ids_hash_as_empty_not_as_the_word_none():
    """`None` rendering as the literal "None" would let a message with the
    literal string run id "None" collide with one that has no run id."""
    common = dict(conversation_id=1, seq=0, role="user", content="x",
                  created_at=T0, turn_id=None, prev_hash=GENESIS)
    assert entry_hash(run_id=None, **common) != entry_hash(run_id="None", **common)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/jc/Documents/Claude/Projects/cyber-agent/cyberguard
make test-env-up >/dev/null 2>&1 || true
python -m pytest tests/test_conversation_chain.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.conversation_chain'`.

- [ ] **Step 3: Write the implementation**

Create `app/services/conversation_chain.py`:

```python
"""Per-conversation hash chain for chat messages.

``audit_logs`` chains globally and pays for it with a single advisory lock that
every write queues behind (``app/core/audit.py:113``). Chat message volume is
orders of magnitude higher, so this chain is scoped to one conversation: a
message links to the previous message *in the same conversation*, and writers
to different conversations never contend.

What that buys and what it does not: the chain proves no message inside a
conversation was altered, reordered or removed. It cannot prove the
conversation itself was not deleted — nothing would be left to be inconsistent.
``app.services.conversation_anchor`` closes that by periodically writing each
chain head into the global audit chain.

Pure and DB-free, like ``app.core.audit_diff``, so the formula can be tested
against the verifier without a database in the way.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional, Sequence

GENESIS = "0" * 64


def _iso(value: Any) -> str:
    """Render a timestamp for hashing.

    The caller passes the value that is (or was) persisted, never a raw input
    string — a digest over something other than the stored value cannot be
    recomputed from the row.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def entry_hash(
    *,
    conversation_id: int,
    seq: int,
    role: str,
    content: str,
    created_at: Any,
    run_id: Optional[str],
    turn_id: Optional[str],
    prev_hash: str,
) -> str:
    """The digest covering everything that makes this message what it is.

    ``backfilled`` is deliberately absent: it describes where the row came
    from, not what was said, and folding it in would make the flag impossible
    to correct later without invalidating the chain.
    """
    body = (
        f"{conversation_id}|{seq}|{role}|{content}|{_iso(created_at)}|"
        f"{run_id or ''}|{turn_id or ''}|{prev_hash}"
    )
    return hashlib.sha256(body.encode()).hexdigest()


def verify_conversation_chain(messages: Sequence[Any]) -> Optional[str]:
    """Describe the first break in one conversation's chain, or None if intact.

    ``messages`` must be the conversation's rows in ascending ``seq`` order.
    Mirrors ``run_event_log.verify_chain``.
    """
    prev = GENESIS
    for expected_seq, message in enumerate(messages):
        if message.seq != expected_seq:
            return f"seq gap: expected {expected_seq}, found {message.seq}"
        if message.prev_hash != prev:
            return f"broken link at seq {message.seq}"
        recomputed = entry_hash(
            conversation_id=message.conversation_id,
            seq=message.seq,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            run_id=message.run_id,
            turn_id=message.turn_id,
            prev_hash=message.prev_hash,
        )
        if recomputed != message.entry_hash:
            return f"content altered at seq {message.seq}"
        prev = message.entry_hash
    return None
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_conversation_chain.py -q
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/conversation_chain.py tests/test_conversation_chain.py
git commit -m "$(cat <<'EOF'
feat: add the per-conversation message hash chain

Scoped to one conversation rather than joined to the global audit chain:
audit_logs serialises every write on pg_advisory_xact_lock(0xA0D17), and
chat volume behind that lock would be a worse bottleneck than the blob
rewrite this replaces.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: The table, the migration, and the backfill

**Files:**
- Create: `app/models/conversation_message.py`
- Create: `app/services/conversation_backfill.py`
- Create: `alembic/versions/041_conversation_messages.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/conversation.py`
- Test: `tests/test_conversation_backfill.py`

**Interfaces:**
- Consumes: `conversation_chain.GENESIS`, `conversation_chain.entry_hash` (Task 1).
- Produces:
  - `app.models.conversation_message.ConversationMessage` — columns `id: int`, `conversation_id: int`, `seq: int`, `role: str`, `content: str`, `run_id: str | None`, `turn_id: str | None`, `created_at: datetime`, `backfilled: bool`, `prev_hash: str`, `entry_hash: str`
  - `Conversation.deleted_at: datetime | None`, `Conversation.last_anchored_seq: int` (default `-1`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_backfill.py`:

```python
"""Migration 041: existing blobs become chained rows, honestly flagged.

The hashes computed here prove only that nothing changed *after* the
migration. The rows are flagged `backfilled` so the trail never claims to
cover the era when the transcript lived in a rewritable blob.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_backfill import rows_for_conversation
from app.services.conversation_chain import verify_conversation_chain


@pytest.mark.asyncio
async def test_a_blob_becomes_a_verifying_chain_of_flagged_rows():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"backfill_{suffix}", email=f"backfill_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(
            user_id=user.id,
            title="imported",
            messages_json=json.dumps([
                {"role": "user", "content": "scan 10.0.0.1",
                 "created_at": "2026-09-01T10:00:00+00:00"},
                {"role": "assistant", "content": "three open ports",
                 "created_at": "2026-09-01T10:00:05+00:00"},
            ]),
        )
        db.add(conv)
        await db.commit()
        conv_id, user_id = conv.id, user.id

        try:
            rows = rows_for_conversation(
                conv_id, conv.messages_json, datetime(2026, 9, 1, 9, 0, 0))
            db.add_all([ConversationMessage(**r) for r in rows])
            await db.commit()

            stored = list((await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conv_id)
                .order_by(ConversationMessage.seq)
            )).scalars().all())

            assert [m.content for m in stored] == ["scan 10.0.0.1", "three open ports"]
            assert [m.role for m in stored] == ["user", "assistant"]
            assert [m.seq for m in stored] == [0, 1]
            assert all(m.backfilled for m in stored), "provenance must be recorded"
            assert verify_conversation_chain(stored) is None
            assert stored[0].created_at.tzinfo is None, "this codebase stores naive UTC"
            assert stored[0].created_at == datetime(2026, 9, 1, 10, 0, 0)
        finally:
            await db.execute(ConversationMessage.__table__.delete().where(
                ConversationMessage.conversation_id == conv_id))
            await db.execute(Conversation.__table__.delete().where(
                Conversation.user_id == user_id))
            await db.execute(User.__table__.delete().where(User.id == user_id))
            await db.commit()


def test_a_message_without_a_timestamp_inherits_the_conversations():
    rows = rows_for_conversation(
        5, json.dumps([{"role": "user", "content": "no timestamp"}]),
        datetime(2026, 1, 1, 0, 0, 0))
    assert rows[0]["created_at"] == datetime(2026, 1, 1, 0, 0, 0)


def test_malformed_blobs_yield_nothing_rather_than_failing_the_migration():
    assert rows_for_conversation(5, "not json", datetime(2026, 1, 1)) == []
    assert rows_for_conversation(5, '{"not": "a list"}', datetime(2026, 1, 1)) == []
    assert rows_for_conversation(5, None, datetime(2026, 1, 1)) == []


def test_non_dict_and_non_string_entries_are_coerced_not_dropped_silently():
    rows = rows_for_conversation(5, json.dumps([
        "a bare string",
        {"role": "assistant", "content": {"structured": "answer"}},
    ]), datetime(2026, 1, 1))
    assert len(rows) == 1, "a non-dict entry has no role and is not a message"
    assert rows[0]["content"] == '{"structured": "answer"}'


def test_seq_is_dense_so_the_chain_verifies_even_when_entries_are_skipped():
    rows = rows_for_conversation(5, json.dumps([
        "skipped", {"role": "user", "content": "a"}, "skipped",
        {"role": "user", "content": "b"},
    ]), datetime(2026, 1, 1))
    assert [r["seq"] for r in rows] == [0, 1]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_backfill.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.conversation_backfill'`.

- [ ] **Step 3: Write the backfill helper**

The helper lives in `app/services/` rather than beside the migration: `alembic/versions/` has no `__init__.py`, so nothing in it is importable from a test, and a migration file named `041_…` starts with a digit and cannot be imported by name either. Create `app/services/conversation_backfill.py`:

```python
"""Pure row-building for migration 041's backfill.

Separated from the migration so it can be tested. The migration calls it and
does the inserting; nothing here touches a database.

Kept after the migration ships: it is what the migration's meaning depends on,
and re-deriving it from a changed chain formula later would silently produce
rows that no longer verify.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.conversation_chain import GENESIS, entry_hash


def _naive_utc(value: Any) -> Optional[datetime]:
    """Parse an ISO timestamp into the naive-UTC form this codebase stores."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def rows_for_conversation(
    conversation_id: int,
    messages_json: Optional[str],
    fallback_created_at: datetime,
) -> List[Dict[str, Any]]:
    """Chained, `backfilled`-flagged rows for one conversation's blob.

    A blob that will not parse yields nothing: a migration that fails on one
    malformed row would block the whole deployment, and the blob is still on
    the conversation row for anyone who wants to look at it.
    """
    try:
        parsed = json.loads(messages_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []

    rows: List[Dict[str, Any]] = []
    prev_hash = GENESIS
    seq = 0
    for message in parsed:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")[:32]
        content = message.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        created_at = _naive_utc(message.get("created_at")) or fallback_created_at
        digest = entry_hash(
            conversation_id=conversation_id, seq=seq, role=role, content=content,
            created_at=created_at, run_id=None, turn_id=None, prev_hash=prev_hash,
        )
        rows.append({
            "conversation_id": conversation_id, "seq": seq, "role": role,
            "content": content, "run_id": None, "turn_id": None,
            "created_at": created_at, "backfilled": True,
            "prev_hash": prev_hash, "entry_hash": digest,
        })
        prev_hash = digest
        seq += 1
    return rows
```

- [ ] **Step 4: Write the model**

Create `app/models/conversation_message.py`:

```python
"""One chat message, chained to the previous message in its conversation.

Append-only: rows are never updated or deleted in normal operation, which is
what makes ``prev_hash`` / ``entry_hash`` meaningful as evidence. Deleting a
conversation from the UI sets ``conversations.deleted_at`` and leaves these
rows alone (see ``app/routers/conversations.py``).
"""
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint, false,
)

from app.core.database import Base
from app.core.time import utc_now


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        # Not merely an index: it is what stops two API workers that computed
        # the same seq from writing a forked chain that still verifies.
        UniqueConstraint("conversation_id", "seq", name="uq_conv_messages_seq"),
        Index("ix_conv_messages_conv_seq", "conversation_id", "seq"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    seq = Column(Integer, nullable=False)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    # Ties a message to the tool-level evidence already in agent_run_events.
    run_id = Column(String(64), nullable=True)
    turn_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    # Outside the hash on purpose: provenance, not content. See conversation_chain.
    backfilled = Column(Boolean, nullable=False, default=False, server_default=false())
    prev_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False)
```

In `app/models/__init__.py`, add the import next to the existing `AgentRunEvent` import and add `"ConversationMessage"` to `__all__`:

```python
from app.models.conversation_message import ConversationMessage
```

In `app/models/conversation.py`, add two columns to `Conversation`, immediately after `updated_at`:

```python
    # Immutability-first: the delete button tombstones the conversation rather
    # than destroying the transcript. Retention decides when rows really go.
    deleted_at = Column(DateTime, nullable=True, default=None)
    # Highest seq already written into the global audit chain by
    # app.services.conversation_anchor. -1 means "nothing anchored yet", which
    # is correct for a conversation whose first message will be seq 0.
    last_anchored_seq = Column(Integer, nullable=False, default=-1, server_default="-1")
```

- [ ] **Step 5: Write the migration**

Create `alembic/versions/041_conversation_messages.py`:

```python
"""Chat messages become append-only, hash-chained rows.

History lived in conversations.messages_json, a single JSON array: every
append rewrote the whole blob, and PUT /conversations/{id} could replace the
transcript in one request. Neither is compatible with the transcript being
evidence of what the assistant said.

Existing blobs are backfilled and every backfilled row is flagged, because
hashes computed here prove only that nothing changed after this migration.
messages_json is left in place — a rollback would otherwise lose history that
exists nowhere else at that moment — and a later migration drops it.

Revision ID: 041_conversation_messages  (≤32 chars: alembic_version.version_num is varchar(32))
Revises: 040_conv_title_no_default
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "041_conversation_messages"
down_revision: Union[str, None] = "040_conv_title_no_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BATCH = 200


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("turn_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("backfilled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_conv_messages_seq"),
    )
    op.create_index("ix_conv_messages_conv_seq", "conversation_messages",
                    ["conversation_id", "seq"])

    op.add_column("conversations", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("conversations", sa.Column(
        "last_anchored_seq", sa.Integer(), nullable=False, server_default="-1"))

    _backfill()


def _backfill() -> None:
    # Imported here rather than at module scope so that a downgrade, or an
    # `alembic history`, does not need the app package importable.
    from app.services.conversation_backfill import rows_for_conversation

    conn = op.get_bind()
    insert = sa.text(
        "INSERT INTO conversation_messages "
        "(conversation_id, seq, role, content, run_id, turn_id, created_at,"
        " backfilled, prev_hash, entry_hash) "
        "VALUES (:conversation_id, :seq, :role, :content, :run_id, :turn_id,"
        " :created_at, :backfilled, :prev_hash, :entry_hash)"
    )

    last_id = 0
    while True:
        batch = conn.execute(sa.text(
            "SELECT id, messages_json, created_at FROM conversations "
            "WHERE id > :last_id AND messages_json IS NOT NULL "
            "AND messages_json NOT IN ('', '[]') "
            "ORDER BY id LIMIT :limit"
        ), {"last_id": last_id, "limit": _BATCH}).fetchall()
        if not batch:
            return
        for conv_id, messages_json, conv_created_at in batch:
            rows = rows_for_conversation(conv_id, messages_json, conv_created_at)
            for row in rows:
                conn.execute(insert, row)
            last_id = conv_id


def downgrade() -> None:
    op.drop_column("conversations", "last_anchored_seq")
    op.drop_column("conversations", "deleted_at")
    op.drop_index("ix_conv_messages_conv_seq", table_name="conversation_messages")
    op.drop_table("conversation_messages")
```

- [ ] **Step 6: Run the migration and the test**

```bash
make test-env-up
DATABASE_URL="$(python -c 'import os;print(os.environ.get("TEST_DATABASE_URL",""))')" \
  python -m alembic -c alembic.ini upgrade head
python -m pytest tests/test_conversation_backfill.py tests/test_alembic_startup.py -q
```

If the `DATABASE_URL` line above does not resolve in this environment, use the Makefile path instead, which sets the test env itself:

```bash
make test
```

Expected: migration applies; 6 new tests pass; `test_alembic_startup.py` still passes.

- [ ] **Step 7: Commit**

```bash
git add app/models/conversation_message.py app/models/conversation.py \
        app/models/__init__.py app/services/conversation_backfill.py \
        alembic/versions/041_conversation_messages.py \
        tests/test_conversation_backfill.py
git commit -m "$(cat <<'EOF'
feat: add the conversation_messages table and backfill existing blobs

Backfilled rows are flagged: hashes computed at migration time prove only
that nothing changed after the migration, and the trail should not claim to
cover the era when the transcript was a rewritable blob.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Cut every read and write over to the table

This is one task because it is one atomic change: the moment appends go to the table, every reader of `messages_json` is stale. Splitting it would leave the app broken between two commits.

**Files:**
- Modify: `app/services/conversation_messages.py` (rewrite the append path, add read helpers)
- Modify: `app/routers/conversations.py:208-230` (`get_conversation_messages`)
- Modify: `app/routers/chat_stream.py:80-96` (history load) and `:172-195` (`_persist_to_conversation`)
- Modify: `app/workers/tasks.py:186-198` (history load)
- Modify: `app/services/internal_agent.py:190-234` (`_load_memory`, `_append_memory`)
- Test: `tests/test_conversation_message_store.py`

**Interfaces:**
- Consumes: `ConversationMessage` (Task 2); `conversation_chain.GENESIS`, `conversation_chain.entry_hash`, `conversation_chain.verify_conversation_chain` (Task 1).
- Produces, all in `app.services.conversation_messages`:
  - `DEFAULT_PAGE_LIMIT: int = 200`, `MAX_PAGE_LIMIT: int = 1000`
  - `async append_messages_locked(session: AsyncSession, conv_id: int, new_messages: Sequence[Dict[str, Any]], *, user_id: Optional[int] = None) -> Tuple[Optional[Conversation], int]` — unchanged signature and return contract (`(conv, total_count)`)
  - `append_messages_locked_sync(session: Session, …) -> Tuple[Optional[Conversation], int]` — sync twin
  - `async fetch_messages(session, conv_id: int, *, limit: int = DEFAULT_PAGE_LIMIT, before_seq: Optional[int] = None) -> List[ConversationMessage]` — ascending `seq`
  - `async fetch_recent(session, conv_id: int, limit: int) -> List[ConversationMessage]` — ascending `seq`, the newest `limit`
  - `fetch_recent_sync(session, conv_id: int, limit: int) -> List[ConversationMessage]`
  - `to_message_dict(row: ConversationMessage) -> Dict[str, Any]` — `{"role", "content", "created_at"}`
  - `to_llm_turns(rows: Sequence[ConversationMessage]) -> List[Dict[str, str]]` — `{"role", "content"}`, user/assistant with non-empty content only
  - retained unchanged: `parse_messages`, `serialize_messages`, `stamp_message`

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_message_store.py`:

```python
"""Appends land in the table, chained, at a cost that does not grow.

The blob this replaces made message n cost the size of messages 1..n-1. These
tests pin both halves of the fix: the chain is real, and the append is O(1).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, select

from app.core.database import AsyncSessionLocal, engine
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_chain import verify_conversation_chain
from app.services.conversation_messages import (
    append_messages_locked,
    fetch_messages,
    fetch_recent,
    to_llm_turns,
    to_message_dict,
)


@pytest.fixture
async def conv():
    """A user and an empty conversation, removed afterwards."""
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"msgstore_{suffix}", email=f"msgstore_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        row = Conversation(user_id=user.id, title="store")
        db.add(row)
        await db.commit()
        ids = (row.id, user.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


async def _append(conv_id, *messages, user_id=None):
    async with AsyncSessionLocal() as db:
        result = await append_messages_locked(db, conv_id, list(messages), user_id=user_id)
        await db.commit()
        return result


@pytest.mark.asyncio
async def test_appending_writes_rows_with_a_dense_verifying_chain(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "scan it"},
                  {"role": "assistant", "content": "done"})

    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)

    assert [r.seq for r in rows] == [0, 1]
    assert [r.content for r in rows] == ["scan it", "done"]
    assert not any(r.backfilled for r in rows)
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_a_second_append_continues_the_same_chain(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "a"})
    _, count = await _append(conv_id, {"role": "assistant", "content": "b"})

    assert count == 2
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert rows[1].prev_hash == rows[0].entry_hash
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_the_stored_timestamp_is_what_the_hash_covers(conv):
    """The digest must be over the persisted datetime, not the caller's string,
    or nothing read back from the table would ever verify."""
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "x",
                            "created_at": "2026-09-01T10:00:00+00:00"})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert rows[0].created_at.tzinfo is None
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_a_message_with_no_content_is_stored_rather_than_dropped(conv):
    """A hole in the transcript is worse than an empty message in it."""
    conv_id, _ = conv
    await _append(conv_id, {"role": "assistant", "content": None})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert [r.content for r in rows] == [""]
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_a_wrong_owner_cannot_append(conv):
    conv_id, user_id = conv
    result, count = await _append(conv_id, {"role": "user", "content": "x"},
                                  user_id=user_id + 99999)
    assert result is None and count == 0


@pytest.mark.asyncio
async def test_an_unknown_conversation_appends_nothing(conv):
    result, count = await _append(2_000_000_000, {"role": "user", "content": "x"})
    assert result is None and count == 0


@pytest.mark.asyncio
async def test_an_empty_append_reports_the_count_without_writing(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "a"})
    _, count = await _append(conv_id)
    assert count == 1


# --- concurrency (spec §7.3) ---

@pytest.mark.asyncio
async def test_two_concurrent_appends_do_not_fork_the_chain(conv):
    """Two API workers appending at once must produce seq 0 and 1, never two
    rows at seq 0. The row lock serialises them; the unique constraint is the
    backstop if it ever does not.
    """
    import asyncio

    conv_id, _ = conv
    await asyncio.gather(
        _append(conv_id, {"role": "user", "content": "first"}),
        _append(conv_id, {"role": "user", "content": "second"}),
    )

    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)

    assert [r.seq for r in rows] == [0, 1]
    assert {r.content for r in rows} == {"first", "second"}
    assert verify_conversation_chain(rows) is None


# --- reads ---

@pytest.mark.asyncio
async def test_fetch_recent_returns_the_newest_in_reading_order(conv):
    conv_id, _ = conv
    await _append(conv_id, *[{"role": "user", "content": str(i)} for i in range(10)])
    async with AsyncSessionLocal() as db:
        rows = await fetch_recent(db, conv_id, 3)
    assert [r.content for r in rows] == ["7", "8", "9"]


@pytest.mark.asyncio
async def test_fetch_messages_pages_backwards_with_before_seq(conv):
    conv_id, _ = conv
    await _append(conv_id, *[{"role": "user", "content": str(i)} for i in range(10)])
    async with AsyncSessionLocal() as db:
        page = await fetch_messages(db, conv_id, limit=3, before_seq=5)
    assert [r.seq for r in page] == [2, 3, 4]


@pytest.mark.asyncio
async def test_to_llm_turns_drops_what_a_model_cannot_use(conv):
    conv_id, _ = conv
    await _append(conv_id,
                  {"role": "user", "content": "keep"},
                  {"role": "system", "content": "drop: not a turn"},
                  {"role": "assistant", "content": ""})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert to_llm_turns(rows) == [{"role": "user", "content": "keep"}]


@pytest.mark.asyncio
async def test_to_message_dict_keeps_the_shape_the_chat_client_expects(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "hi"})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert set(to_message_dict(rows[0])) == {"role", "content", "created_at"}
    assert isinstance(to_message_dict(rows[0])["created_at"], str)


# --- cost (spec §7.6) ---

@pytest.mark.asyncio
async def test_appending_costs_the_same_at_message_500_as_at_message_1(conv):
    """The property the whole table exists for.

    Measured in statements issued and parameter bytes bound, not wall clock,
    so it does not flake on a loaded machine.
    """
    conv_id, _ = conv

    captured: list[tuple[str, int]] = []

    def record(_conn, _cursor, statement, parameters, _context, _executemany):
        captured.append((statement, len(str(parameters))))

    async def measure(target_conv_id):
        captured.clear()
        event.listen(engine.sync_engine, "before_cursor_execute", record)
        try:
            await _append(target_conv_id, {"role": "user", "content": "identical payload"})
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)
        return len(captured), sum(size for _, size in captured)

    empty_statements, empty_bytes = await measure(conv_id)

    await _append(conv_id, *[{"role": "user", "content": "filler"} for _ in range(500)])
    long_statements, long_bytes = await measure(conv_id)

    assert long_statements == empty_statements, (
        f"appending to a long conversation issued {long_statements} statements "
        f"vs {empty_statements} to a short one — something scans the history"
    )
    assert long_bytes == empty_bytes, (
        "the append writes more bytes as the history grows, which is the blob "
        "behaviour this table replaces"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_message_store.py -q
```

Expected: collection error — `ImportError: cannot import name 'fetch_messages' from 'app.services.conversation_messages'`.

- [ ] **Step 3: Rewrite the store**

Replace the body of `app/services/conversation_messages.py` below the existing `stamp_message` function, and replace its module docstring. Keep `parse_messages`, `serialize_messages` and `stamp_message` exactly as they are — `tests/test_conversation_messages.py` covers them and the blob still has to be readable.

New module docstring:

```python
"""Append-only, hash-chained storage for chat messages.

History used to be ``conversations.messages_json``, one JSON array rewritten on
every append, so message n cost the size of messages 1..n-1. Each message is
now a row in ``conversation_messages``, chained to the previous message in the
same conversation (``app.services.conversation_chain``).

The conversation row is still locked (``SELECT … FOR UPDATE``) while appending.
That lock no longer exists to protect a read-modify-write of the blob; it
serialises the readers of the chain head, so two workers cannot compute the
same ``seq``. ``uq_conv_messages_seq`` is the backstop if it ever fails to.
"""
```

Append to the file (the sync twin mirrors the async one — this codebase keeps
sync twins for Celery rather than bridging loops):

```python
DEFAULT_PAGE_LIMIT = 200
MAX_PAGE_LIMIT = 1000

# Roles a chat model can be replayed with. Other roles are stored — the
# transcript records everything that happened — but not sent back to a model.
_LLM_ROLES = ("user", "assistant")


def _coerce_created_at(value: Any) -> datetime:
    """Normalise to the naive-UTC datetime this codebase stores.

    The chain hashes the value returned here, i.e. the value that lands in the
    column, so that a row read back can be re-verified.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return utc_now()
    else:
        return utc_now()
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _build_rows(
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    next_seq: int,
    prev_hash: str,
) -> List[ConversationMessage]:
    rows: List[ConversationMessage] = []
    seq = next_seq
    for message in new_messages:
        role = str(message.get("role") or "")[:32]
        content = message.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        created_at = _coerce_created_at(message.get("created_at"))
        run_id = message.get("run_id")
        turn_id = message.get("turn_id")
        digest = entry_hash(
            conversation_id=conv_id, seq=seq, role=role, content=content,
            created_at=created_at, run_id=run_id, turn_id=turn_id,
            prev_hash=prev_hash,
        )
        rows.append(ConversationMessage(
            conversation_id=conv_id, seq=seq, role=role, content=content,
            run_id=run_id, turn_id=turn_id, created_at=created_at,
            backfilled=False, prev_hash=prev_hash, entry_hash=digest,
        ))
        prev_hash = digest
        seq += 1
    return rows


def _head_statement(conv_id: int):
    return (
        select(ConversationMessage.seq, ConversationMessage.entry_hash)
        .where(ConversationMessage.conversation_id == conv_id)
        .order_by(ConversationMessage.seq.desc())
        .limit(1)
    )


def _conversation_statement(conv_id: int, user_id: Optional[int], lock: bool):
    stmt = select(Conversation).where(Conversation.id == conv_id)
    if user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    return stmt.with_for_update() if lock else stmt


async def append_messages_locked(
    session: AsyncSession,
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    *,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Conversation], int]:
    """Append messages under row lock. Returns (conv, total_count) or (None, 0)."""
    conv = (await session.execute(
        _conversation_statement(conv_id, user_id, bool(new_messages))
    )).scalar_one_or_none()
    if not conv:
        return None, 0

    head = (await session.execute(_head_statement(conv_id))).first()
    next_seq = 0 if head is None else head[0] + 1
    prev_hash = GENESIS if head is None else head[1]

    if not new_messages:
        return conv, next_seq

    rows = _build_rows(conv_id, new_messages, next_seq, prev_hash)
    session.add_all(rows)
    conv.updated_at = utc_now()
    return conv, next_seq + len(rows)


def append_messages_locked_sync(
    session: Session,
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    *,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Conversation], int]:
    """Sync variant for Celery workers."""
    conv = session.execute(
        _conversation_statement(conv_id, user_id, bool(new_messages))
    ).scalar_one_or_none()
    if not conv:
        return None, 0

    head = session.execute(_head_statement(conv_id)).first()
    next_seq = 0 if head is None else head[0] + 1
    prev_hash = GENESIS if head is None else head[1]

    if not new_messages:
        return conv, next_seq

    rows = _build_rows(conv_id, new_messages, next_seq, prev_hash)
    session.add_all(rows)
    conv.updated_at = utc_now()
    return conv, next_seq + len(rows)


# -------- reads --------

def _page_statement(conv_id: int, limit: int, before_seq: Optional[int]):
    stmt = select(ConversationMessage).where(
        ConversationMessage.conversation_id == conv_id)
    if before_seq is not None:
        stmt = stmt.where(ConversationMessage.seq < before_seq)
    return stmt.order_by(ConversationMessage.seq.desc()).limit(
        max(1, min(int(limit), MAX_PAGE_LIMIT)))


async def fetch_messages(
    session: AsyncSession,
    conv_id: int,
    *,
    limit: int = DEFAULT_PAGE_LIMIT,
    before_seq: Optional[int] = None,
) -> List[ConversationMessage]:
    """The newest ``limit`` messages before ``before_seq``, in reading order."""
    rows = (await session.execute(
        _page_statement(conv_id, limit, before_seq))).scalars().all()
    return list(reversed(rows))


async def fetch_recent(
    session: AsyncSession, conv_id: int, limit: int
) -> List[ConversationMessage]:
    return await fetch_messages(session, conv_id, limit=limit)


def fetch_recent_sync(
    session: Session, conv_id: int, limit: int
) -> List[ConversationMessage]:
    rows = session.execute(_page_statement(conv_id, limit, None)).scalars().all()
    return list(reversed(rows))


def to_message_dict(row: ConversationMessage) -> Dict[str, Any]:
    """The shape the chat client has always received."""
    return {
        "role": row.role,
        "content": row.content,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def to_llm_turns(rows: Sequence[ConversationMessage]) -> List[Dict[str, str]]:
    """Replayable turns only — the filter the callers used to apply inline."""
    return [
        {"role": row.role, "content": row.content}
        for row in rows
        if row.role in _LLM_ROLES and row.content
    ]
```

Update the imports at the top of the file to:

```python
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.services.conversation_chain import GENESIS, entry_hash
```

- [ ] **Step 4: Run the store test**

```bash
python -m pytest tests/test_conversation_message_store.py tests/test_conversation_messages.py -q
```

Expected: all pass.

- [ ] **Step 5: Switch the router's read**

In `app/routers/conversations.py`, replace the body of `get_conversation_messages` after the 404 check (currently `json.loads(conv.messages_json …)`) with the paged read, and add `limit`/`before_seq` query parameters to the signature:

```python
@router.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(
    conv_id: int,
    limit: int = DEFAULT_PAGE_LIMIT,
    before_seq: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Get messages for a conversation, newest-last, most recent page first."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    rows = await fetch_messages(db, conv_id, limit=limit, before_seq=before_seq)
    return {"messages": [to_message_dict(row) for row in rows]}
```

Add to the imports at the top of `app/routers/conversations.py`:

```python
from app.services.conversation_messages import (
    DEFAULT_PAGE_LIMIT,
    fetch_messages,
    to_message_dict,
)
```

- [ ] **Step 6: Switch the streaming chat path**

In `app/routers/chat_stream.py`, replace the history load (the `msgs = _json.loads(conversation.messages_json or "[]")` block) with:

```python
            if conversation:
                async with AsyncSessionLocal() as session:
                    rows = await fetch_recent(session, body.conversation_id, 20)
                conversation_history = to_llm_turns(rows)
```

and replace the whole read-modify-write inside `_persist_to_conversation` (the block from `messages = _json.loads(conv.messages_json or "[]")` through `conv.updated_at = utc_now()`) with:

```python
            conv, _ = await append_messages_locked(
                session,
                conversation_id,
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_response},
                ],
                user_id=user_id,
            )
            if not conv:
                return
```

removing the now-dead `select(Conversation)` lookup immediately above it, since
`append_messages_locked` performs the lookup and the ownership check itself.
This also fixes a pre-existing defect: the replaced code did a read-modify-write
with **no** `FOR UPDATE`, so a concurrent append was silently lost under
`API_WORKERS>1`.

Add to that file's imports:

```python
from app.services.conversation_messages import (
    append_messages_locked, fetch_recent, to_llm_turns,
)
```

- [ ] **Step 7: Switch the Celery worker's read**

In `app/workers/tasks.py`, replace the `all_messages = _json.loads(conv.messages_json or "[]")` try/except block inside `_run_async_master_agent` with:

```python
            # Conversation history: last 20 messages (10 turns) so the LLM has
            # memory without blowing the context window.
            from app.services.conversation_messages import (
                fetch_recent_sync, to_llm_turns,
            )
            with SessionLocal() as session:
                conversation_history = to_llm_turns(
                    fetch_recent_sync(session, conversation_id, 20))
```

- [ ] **Step 8: Switch the internal agent's memory slice**

In `app/services/internal_agent.py`, replace the body of `_load_memory` after the `parent_conversation_id is None` guard with:

```python
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Conversation).where(
                    Conversation.parent_conversation_id == parent_conversation_id,
                    Conversation.agent_id == self.agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return []
            from app.services.conversation_messages import (
                fetch_recent, to_message_dict,
            )
            rows = await fetch_recent(s, row.id, self.memory_window)
            return [to_message_dict(m) for m in rows]
```

and replace the body of `_append_memory` after its guard with:

```python
        from app.services.conversation_messages import append_messages_locked

        async with AsyncSessionLocal() as s:
            row = await self._get_or_create_slice_row(s, parent_conversation_id, user_id)
            await s.flush()
            await append_messages_locked(s, row.id, [dict(m) for m in messages])
            await s.commit()
```

This is where the performance win lands for internal agents: the old code loaded
every message ever stored on the slice and then kept the last `memory_window`.

- [ ] **Step 9: Run the full suite**

```bash
make test
```

Expected: all pass. If `tests/test_chat_stream*.py`, `tests/test_internal_agent*.py` or `tests/test_agent_*` fail because they seeded `messages_json` directly, update those fixtures to append through `append_messages_locked` — seeding the blob no longer populates history, and that is the intended behaviour, not a regression to work around.

- [ ] **Step 10: Commit**

```bash
git add app/services/conversation_messages.py app/routers/conversations.py \
        app/routers/chat_stream.py app/workers/tasks.py \
        app/services/internal_agent.py tests/test_conversation_message_store.py
git commit -m "$(cat <<'EOF'
feat: store chat messages as rows, not as a rewritten blob

Appending is now one INSERT whatever the history length, and reads are
pageable. chat_stream's persist path also stops doing an unlocked
read-modify-write, which silently lost a concurrent append under
API_WORKERS>1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Close the rewrite hole and tombstone deletes

**Files:**
- Modify: `app/routers/conversations.py` (`ConversationResponse`, `ConversationUpdate`, `_REQUIRED_UPDATE_FIELDS`, `list_conversations`, `delete_conversation`)
- Test: `tests/test_conversation_immutability.py`

**Interfaces:**
- Consumes: `ConversationMessage` (Task 2); `append_messages_locked` (Task 3, in the test fixture only).
- Produces: `ConversationResponse` without `messages_json`, with `message_count: int = 0` and `last_message_preview: Optional[str] = None`; `Conversation.deleted_at` set by `DELETE /conversations/{id}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_immutability.py`:

```python
"""The transcript cannot be rewritten or erased through the API.

PUT /conversations/{id} used to take `messages_json` as a plain string and
write it verbatim: one request replaced the whole transcript, and nothing
recorded that it happened. For a product whose point is evidence of what the
AI said, that is the hole worth closing first.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.routers.conversations import (
    ConversationResponse,
    ConversationUpdate,
    delete_conversation,
    list_conversations,
    update_conversation,
)
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def seeded():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"immut_{suffix}", email=f"immut_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="evidence")
        db.add(conv)
        await db.commit()
        await append_messages_locked(db, conv.id, [
            {"role": "user", "content": "is 10.0.0.1 safe to expose"},
            {"role": "assistant", "content": "yes, it is safe"},
        ])
        await db.commit()
        ids = (conv.id, user.id, user.username, user.email, user.role)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


def _user(seeded):
    _, user_id, username, email, role = seeded
    return AuthenticatedUser(user_id=user_id, username=username, email=email, role=role)


def test_the_update_schema_has_no_message_content_field():
    assert "messages_json" not in ConversationUpdate.model_fields, (
        "a message-content field on the update schema is a one-request "
        "transcript rewrite"
    )


def test_the_response_schema_no_longer_ships_the_whole_transcript():
    assert "messages_json" not in ConversationResponse.model_fields


def test_an_unknown_field_on_the_update_is_ignored_not_written():
    body = ConversationUpdate.model_validate(
        {"title": "kept", "messages_json": '[{"role":"assistant","content":"forged"}]'})
    assert body.model_dump(exclude_unset=True) == {"title": "kept"}


@pytest.mark.asyncio
async def test_an_update_cannot_change_a_single_message(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        await update_conversation(
            conv_id,
            ConversationUpdate.model_validate({
                "title": "renamed",
                "messages_json": '[{"role":"assistant","content":"no, it is unsafe"}]',
            }),
            db, _user(seeded))
        await db.commit()

        rows = list((await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv_id)
            .order_by(ConversationMessage.seq))).scalars().all())

    assert [r.content for r in rows] == [
        "is 10.0.0.1 safe to expose", "yes, it is safe"]


@pytest.mark.asyncio
async def test_deleting_keeps_the_messages_and_tombstones_the_conversation(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        await delete_conversation(conv_id, db, _user(seeded))
        await db.commit()

        conv = (await db.execute(select(Conversation).where(
            Conversation.id == conv_id))).scalar_one_or_none()
        surviving = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == conv_id))).scalars().all()

    assert conv is not None, "the conversation row must survive as a tombstone"
    assert conv.deleted_at is not None
    assert conv.deleted_at.tzinfo is None
    assert len(surviving) == 2, "a user must not be able to erase what the AI said"


@pytest.mark.asyncio
async def test_a_tombstoned_conversation_is_hidden_from_the_list(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        await delete_conversation(conv_id, db, _user(seeded))
        await db.commit()
        listed = await list_conversations(db, _user(seeded))
    assert all(c.id != conv_id for c in listed)


@pytest.mark.asyncio
async def test_the_list_reports_a_count_and_a_preview_instead_of_every_message(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        listed = await list_conversations(db, _user(seeded))
    row = next(c for c in listed if c.id == conv_id)
    assert row.message_count == 2
    assert row.last_message_preview == "yes, it is safe"


@pytest.mark.asyncio
async def test_an_empty_conversation_lists_without_a_preview(seeded):
    _, user_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        empty = Conversation(user_id=user_id, title="nothing said yet")
        db.add(empty)
        await db.commit()
        listed = await list_conversations(db, _user(seeded))
    row = next(c for c in listed if c.title == "nothing said yet")
    assert row.message_count == 0
    assert row.last_message_preview is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_immutability.py -q
```

Expected: FAIL — `test_the_update_schema_has_no_message_content_field` fails on the assertion, and the delete tests fail because the row is gone.

- [ ] **Step 3: Change the schemas**

In `app/routers/conversations.py`:

Delete the `messages_json: str` line from `ConversationResponse` and add:

```python
    # The transcript is no longer shipped with the list: it made every listing
    # carry every message of 50 conversations. Read it from
    # GET /conversations/{id}/messages, a page at a time.
    message_count: int = 0
    last_message_preview: Optional[str] = None
```

Delete the `messages_json: Optional[str] = None` line from `ConversationUpdate`
(with its comment). Pydantic ignores unknown fields by default, so a client that
still sends it is simply not writing anything.

Narrow the guard that stops a null from blanking a field:

```python
_REQUIRED_UPDATE_FIELDS = {"title"}
```

- [ ] **Step 4: Compute the count and preview in the listing**

Replace the body of `list_conversations`:

```python
@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """List the caller's live conversations, newest first."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(desc(Conversation.updated_at))
        .limit(50)
    )
    conversations = list(result.scalars().all())
    if not conversations:
        return []

    ids = [c.id for c in conversations]

    counts = dict((await db.execute(
        select(ConversationMessage.conversation_id, func.count(ConversationMessage.id))
        .where(ConversationMessage.conversation_id.in_(ids))
        .group_by(ConversationMessage.conversation_id)
    )).all())

    # DISTINCT ON is PostgreSQL-only, which this deployment is. It gets the
    # newest message per conversation in one pass instead of one query each.
    previews = dict((await db.execute(
        select(ConversationMessage.conversation_id, ConversationMessage.content)
        .where(ConversationMessage.conversation_id.in_(ids))
        .distinct(ConversationMessage.conversation_id)
        .order_by(ConversationMessage.conversation_id, ConversationMessage.seq.desc())
    )).all())

    responses = []
    for conv in conversations:
        payload = ConversationResponse.model_validate(conv)
        payload.message_count = counts.get(conv.id, 0)
        preview = previews.get(conv.id)
        payload.last_message_preview = preview[:200] if preview else None
        responses.append(payload)
    return responses
```

Add to that file's imports:

```python
from sqlalchemy import func
from app.models.conversation_message import ConversationMessage
```

- [ ] **Step 5: Make the delete a tombstone**

Replace the last two lines of `delete_conversation` (`await db.delete(conv)` / `await db.commit()`) with:

```python
    # Immutability-first: a user removing a conversation from their sidebar
    # must not be able to destroy the record of what the assistant told them.
    # Retention (Round 3) decides when the rows actually go.
    conv.deleted_at = utc_now()
    await db.commit()
```

Add the same `deleted_at.is_(None)` filter to the `select(Conversation)` in
`get_conversation`, `update_conversation` and `get_conversation_messages`, so a
tombstoned conversation reads as a 404 everywhere rather than only in the list.

- [ ] **Step 6: Run the tests**

```bash
python -m pytest tests/test_conversation_immutability.py tests/test_conversation_update.py -q
```

Expected: all pass. `test_conversation_update.py`'s `SimpleNamespace` fixtures
still carry a `messages_json` attribute; that is harmless — `apply_conversation_update`
now never touches it.

- [ ] **Step 7: Commit**

```bash
git add app/routers/conversations.py tests/test_conversation_immutability.py
git commit -m "$(cat <<'EOF'
feat: stop the API from rewriting or erasing a transcript

PUT /conversations/{id} accepted messages_json and wrote it verbatim, so one
request replaced a whole transcript with nothing recorded. The field is gone,
and DELETE now tombstones the conversation instead of destroying the messages.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Anchor each chain head into the global audit chain

A per-conversation chain proves nothing was altered *inside* a conversation. Deleting every row of one chain leaves nothing inconsistent, so the head is periodically written into `audit_logs`.

**Files:**
- Modify: `app/core/audit.py` (add `record_action_sync`)
- Create: `app/services/conversation_anchor.py`
- Modify: `app/workers/tasks.py` (task + beat entry)
- Test: `tests/test_conversation_anchor.py`

**Interfaces:**
- Consumes: `ConversationMessage`, `Conversation.last_anchored_seq` (Task 2); `append_messages_locked` (Task 3).
- Produces:
  - `app.core.audit.record_action_sync(*, user_id, action, agent_name=None, action_category=None, risk_tier=None, confidence=None, human_reviewer=None, rollback_possible=None, input_data=None, output_data=None, agent_id=None, request_id=None) -> dict` — the sync twin of `record_action`
  - `app.services.conversation_anchor.ANCHOR_ACTION: str = "conversation.chain_anchor"`
  - `app.services.conversation_anchor.anchor_pending(session: Session, *, limit: int = 500) -> Dict[str, int]` — returns `{"anchored": n}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_anchor.py`:

```python
"""Anchoring: what makes a deleted conversation detectable.

The per-conversation chain proves no message inside a conversation was
altered, reordered or removed. It cannot prove the conversation existed —
delete every row and nothing is left to be inconsistent. Writing each chain
head into the global audit chain is what closes that.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, get_sync_session
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_anchor import ANCHOR_ACTION, anchor_pending
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def seeded():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"anchor_{suffix}", email=f"anchor_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="anchored")
        db.add(conv)
        await db.commit()
        await append_messages_locked(db, conv.id, [
            {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
        await db.commit()
        ids = (conv.id, user.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(AuditLog.__table__.delete().where(AuditLog.user_id == ids[1]))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


def _run_anchor():
    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        summary = anchor_pending(session)
        session.commit()
    return summary


@pytest.mark.asyncio
async def test_anchoring_records_the_head_and_advances_the_marker(seeded):
    conv_id, user_id = seeded
    assert _run_anchor()["anchored"] >= 1

    async with AsyncSessionLocal() as db:
        conv = (await db.execute(select(Conversation).where(
            Conversation.id == conv_id))).scalar_one()
        head = (await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv_id)
            .order_by(ConversationMessage.seq.desc()).limit(1))).scalar_one()
        anchors = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == user_id, AuditLog.action == ANCHOR_ACTION))).scalars().all()

    assert conv.last_anchored_seq == head.seq == 1
    assert len(anchors) == 1
    assert anchors[0].entry_hash and anchors[0].prev_hash


@pytest.mark.asyncio
async def test_a_second_run_with_nothing_new_writes_nothing(seeded):
    conv_id, user_id = seeded
    _run_anchor()
    before = _count_anchors_sync(user_id)
    assert _run_anchor()["anchored"] == 0
    assert _count_anchors_sync(user_id) == before


def _count_anchors_sync(user_id: int) -> int:
    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        return len(session.execute(select(AuditLog).where(
            AuditLog.user_id == user_id,
            AuditLog.action == ANCHOR_ACTION)).scalars().all())


@pytest.mark.asyncio
async def test_new_messages_after_an_anchor_produce_another_one(seeded):
    conv_id, user_id = seeded
    _run_anchor()
    async with AsyncSessionLocal() as db:
        await append_messages_locked(db, conv_id, [{"role": "user", "content": "c"}])
        await db.commit()
    assert _run_anchor()["anchored"] >= 1
    assert _count_anchors_sync(user_id) == 2


@pytest.mark.asyncio
async def test_a_conversation_with_no_messages_is_not_anchored(seeded):
    """-1 as the starting marker must not read as "seq 0 is pending"."""
    _, user_id = seeded
    async with AsyncSessionLocal() as db:
        empty = Conversation(user_id=user_id, title="silent")
        db.add(empty)
        await db.commit()
        empty_id = empty.id
    _run_anchor()
    async with AsyncSessionLocal() as db:
        conv = (await db.execute(select(Conversation).where(
            Conversation.id == empty_id))).scalar_one()
    assert conv.last_anchored_seq == -1


@pytest.mark.asyncio
async def test_the_anchor_stays_in_the_global_chain(seeded):
    """An anchor is an ordinary audit row: if it broke the chain it would be
    worse than not anchoring at all."""
    from app.core.audit import verify_chain

    _run_anchor()
    ok, broken_at = await verify_chain()
    assert ok, f"anchoring broke the global audit chain at row {broken_at}"


def test_the_sync_audit_writer_links_to_the_same_chain():
    """record_action_sync exists because Celery is sync; it must produce rows
    indistinguishable from record_action's."""
    from app.core.audit import record_action_sync

    payload = record_action_sync(
        user_id=None, action="test.sync_chain_writer",
        action_category="annotate", input_data={"a": 1}, output_data={"b": 2})
    assert len(payload["entry_hash"]) == 64
    assert len(payload["prev_hash"]) == 64
    assert payload["chain_version"] == 2
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_anchor.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.conversation_anchor'`.

- [ ] **Step 3: Add the sync audit writer**

Append to `app/core/audit.py`, directly after `record_action`:

```python
def record_action_sync(
    *, user_id, action, agent_name=None, action_category=None,
    risk_tier=None, confidence=None, human_reviewer=None,
    rollback_possible=None, input_data=None, output_data=None,
    agent_id=None, request_id=None,
) -> dict:
    """Sync twin of ``record_action``, for Celery workers.

    Celery tasks in this codebase use ``get_sync_session`` rather than bridging
    into the async engine (see ``cleanup_stale_executions_task``), and the same
    reasoning gives ``conversation_messages`` a sync append twin.

    ``_chain_lock`` has no counterpart here, and needs none: it only serialises
    coroutines inside one event loop. ``pg_advisory_xact_lock`` is what makes
    the chain correct across processes, and that is taken below.
    """
    from app.core.database import get_sync_session

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = _chain_payload(
        user_id=user_id, agent_id=agent_id, agent_name=agent_name, action=action,
        action_category=action_category,
        confidence=None if confidence is None else f"{float(confidence):.4f}",
        human_reviewer=human_reviewer, rollback_possible=rollback_possible,
        risk_tier=risk_tier, input_hash=_hash_data(input_data),
        output_hash=_hash_data(output_data),
        request_id=request_id or _generate_request_id(), timestamp=timestamp,
    )

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        session.execute(select(func.pg_advisory_xact_lock(0xA0D17)))
        prev = session.execute(
            select(AuditLog.entry_hash)
            .where(AuditLog.entry_hash.is_not(None))
            .order_by(AuditLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        prev_hash = prev or _GENESIS
        payload = stamp_chain_hashes(payload, prev_hash)

        session.add(AuditLog(
            user_id=user_id, agent_id=(str(agent_id) if agent_id is not None else None),
            agent_name=agent_name, action=action, action_category=action_category,
            confidence=payload["confidence"], human_reviewer=human_reviewer,
            rollback_possible=rollback_possible, risk_tier=risk_tier,
            input_hash=payload["input_hash"], output_hash=payload["output_hash"],
            request_id=payload["request_id"], prev_hash=prev_hash,
            entry_hash=payload["entry_hash"], timestamp=timestamp,
            chain_version=_CHAIN_VERSION,
        ))
        session.commit()
    return payload
```

- [ ] **Step 4: Write the anchor service**

Create `app/services/conversation_anchor.py`:

```python
"""Write each conversation's chain head into the global audit chain.

``conversation_chain`` gives each conversation its own chain, which is what
keeps chat writes off the global audit advisory lock. The cost of that choice
is that a chain proves nothing about its own existence: delete every row of one
and nothing is left to be inconsistent.

This periodically records a head — conversation id, head seq, head hash — as an
ordinary audit row. One row per *active* conversation per interval, not per
message, which is the volume the global lock can absorb.

What it does not cover: messages appended after the last anchor and removed
before the next. That window is the schedule, not the design.
"""
from __future__ import annotations

import logging
from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_action_sync
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

logger = logging.getLogger(__name__)

ANCHOR_ACTION = "conversation.chain_anchor"


def anchor_pending(session: Session, *, limit: int = 500) -> Dict[str, int]:
    """Anchor every conversation whose head has moved since it was last anchored."""
    heads = (
        select(
            ConversationMessage.conversation_id.label("cid"),
            func.max(ConversationMessage.seq).label("head_seq"),
        )
        .group_by(ConversationMessage.conversation_id)
        .subquery()
    )
    pending = session.execute(
        select(Conversation, heads.c.head_seq)
        .join(heads, heads.c.cid == Conversation.id)
        .where(heads.c.head_seq > Conversation.last_anchored_seq)
        .order_by(Conversation.id)
        .limit(limit)
    ).all()

    anchored = 0
    for conv, head_seq in pending:
        head = session.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.seq == head_seq,
            )
        ).scalar_one_or_none()
        if head is None:
            # The head moved between the two queries; the next run catches it.
            continue

        backfilled_through = session.execute(
            select(func.max(ConversationMessage.seq)).where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.backfilled.is_(True),
            )
        ).scalar_one_or_none()

        # The audit row is written first and the marker advanced second: if the
        # process dies between them the next run writes a duplicate anchor,
        # which is harmless. The other order would lose one silently.
        record_action_sync(
            user_id=conv.user_id,
            action=ANCHOR_ACTION,
            action_category="annotate",
            rollback_possible=False,
            input_data={
                "conversation_id": conv.id,
                "from_seq": conv.last_anchored_seq + 1,
            },
            output_data={
                "head_seq": head.seq,
                "head_hash": head.entry_hash,
                "backfilled_through": backfilled_through,
            },
        )
        conv.last_anchored_seq = head.seq
        anchored += 1

    if anchored:
        logger.info("[conversation_anchor] anchored %d conversation chain(s)", anchored)
    return {"anchored": anchored}
```

- [ ] **Step 5: Wire it to the beat schedule**

Append to `app/workers/tasks.py`, next to `cleanup_stale_executions_task`:

```python
@celery_app.task(bind=True, max_retries=1)
def anchor_conversation_chains_task(self):
    """Write moved conversation chain heads into the global audit chain.

    Sync, like every other beat task here: Celery has no event loop of its own,
    and `get_sync_session` avoids binding the shared async engine to a
    throwaway loop.
    """
    from app.core.database import get_sync_session
    from app.services.conversation_anchor import anchor_pending

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        summary = anchor_pending(session)
        session.commit()
    return summary
```

and add the entry to `celery_app.conf.beat_schedule`:

```python
    "anchor-conversation-chains-every-15-min": {
        "task": "app.workers.tasks.anchor_conversation_chains_task",
        "schedule": 900.0,  # 15 minutes
    },
```

- [ ] **Step 6: Run the tests**

```bash
python -m pytest tests/test_conversation_anchor.py tests/test_audit_chain.py -q
```

Expected: all pass. `test_audit_chain.py` must stay green — the sync writer shares the chain with the async one.

- [ ] **Step 7: Commit**

```bash
git add app/core/audit.py app/services/conversation_anchor.py \
        app/workers/tasks.py tests/test_conversation_anchor.py
git commit -m "$(cat <<'EOF'
feat: anchor conversation chain heads into the global audit chain

A per-conversation chain cannot prove its own existence: delete every row and
nothing is left to be inconsistent. One anchor per active conversation per
15 minutes is a volume the global advisory lock can absorb, unlike one per
message.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Frontend — stop reading a field that no longer exists

`GlobalSearch` parsed `messages_json` client-side to build previews. That field is gone from the list response, so it must read the new `last_message_preview`. This is the temporary search degradation the spec names in §5: until Round 2 there is no full-text message search, only title and preview matching.

**Files:**
- Modify: `webui/src/api/client.ts:308` (drop `messages_json` from `updateConversation`)
- Modify: `webui/src/components/GlobalSearch.tsx:81,158-170`
- Test: `webui/src/components/GlobalSearch.test.tsx` (create if absent; otherwise extend)

**Interfaces:**
- Consumes: `ConversationResponse` with `message_count` and `last_message_preview` (Task 4).
- Produces: no new exports.

- [ ] **Step 1: Write the failing test**

Create `webui/src/components/GlobalSearch.conversations.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { api } from '../api/client'
import GlobalSearch from './GlobalSearch'

/**
 * The conversation list no longer carries every message. Until Round 2 adds a
 * server-side message search, this pane matches titles and the server-rendered
 * preview — and must not crash on the absent field.
 */
describe('GlobalSearch conversations', () => {
  beforeEach(() => {
    for (const name of [
      'getAgents', 'getProviders', 'getSkills', 'getTools', 'getKnowledgeBases',
      'getMCPServers', 'getPromptTemplates',
    ] as const) {
      vi.spyOn(api, name).mockResolvedValue([] as never)
    }
  })

  it('shows the server-rendered preview and count', async () => {
    vi.spyOn(api, 'getConversations').mockResolvedValue([
      { id: 4, title: 'Port scan triage', message_count: 12,
        last_message_preview: 'three open ports' },
    ] as never)

    render(<GlobalSearch open onClose={() => {}} setTab={() => {}} recentTabs={[]} />)

    await waitFor(() => expect(screen.getByText('Port scan triage')).toBeTruthy())
    expect(screen.getByText(/12 messages/)).toBeTruthy()
  })

  it('renders a conversation with no messages without crashing', async () => {
    vi.spyOn(api, 'getConversations').mockResolvedValue([
      { id: 5, title: 'Empty', message_count: 0, last_message_preview: null },
    ] as never)

    render(<GlobalSearch open onClose={() => {}} setTab={() => {}} recentTabs={[]} />)

    await waitFor(() => expect(screen.getByText('Empty')).toBeTruthy())
    expect(screen.getByText(/EMPTY/)).toBeTruthy()
  })
})
```

`GlobalSearch`'s props are `open: boolean`, `onClose: () => void`, `setTab: (t: Tab) => void` and `recentTabs: Tab[]` (`webui/src/components/GlobalSearch.tsx:21-26`). Do not change the component's signature to suit the test.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd webui && npx vitest run src/components/GlobalSearch.conversations.test.tsx
```

Expected: FAIL — the preview is empty because the component still parses `messages_json`.

- [ ] **Step 3: Update the component**

In `webui/src/components/GlobalSearch.tsx`, replace the `ConvRow` type:

```tsx
      type ConvRow = {
        id: number
        title?: string
        message_count?: number
        last_message_preview?: string | null
      }
```

and replace the conversation loop body (the `let msgs` … `items.push` block) with:

```tsx
      if (convos.status === 'fulfilled') {
        for (const c of unwrapList<ConvRow>(convos.value, 'conversations')) {
          const count = c.message_count ?? 0
          items.push({
            id: c.id,
            name: c.title || `Conversation #${c.id}`,
            subtitle: count > 0 ? `${count} messages` : 'EMPTY',
            tab: 'chat',
            category: 'CONVERSATIONS',
            icon: '◉',
            // The transcript is no longer shipped with the listing. Full-text
            // search over messages arrives with the server-side endpoint.
            preview: c.last_message_preview || '',
          })
        }
      }
```

In `webui/src/api/client.ts`, delete the `messages_json?: string` line from `updateConversation`'s body type. No caller passes it — `Chat.tsx:348` sends `{ title }` and `Chat.tsx:910` sends only the override fields.

- [ ] **Step 4: Run the frontend gates**

```bash
cd webui && npx vitest run
cd webui && npx tsc --noEmit -p tsconfig.app.json && npx tsc --noEmit -p tsconfig.test.json
```

Expected: all tests pass, both typecheck targets clean.

- [ ] **Step 5: Commit**

```bash
git add webui/src/components/GlobalSearch.tsx \
        webui/src/components/GlobalSearch.conversations.test.tsx \
        webui/src/api/client.ts
git commit -m "$(cat <<'EOF'
fix: read the server-rendered conversation preview

The listing no longer ships every message, so the search pane reads
message_count and last_message_preview. Full-text search over messages
returns with the server-side endpoint in Round 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: INV-43 as an enforced invariant

**Files:**
- Modify: `tests/test_invariants_static.py`
- Modify: `docs/delivery/ARCHITECTURE_AND_SECURITY.md`

**Interfaces:**
- Consumes: everything above.
- Produces: no new exports.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_invariants_static.py`:

```python
# INV-43 · the assistant's words are evidence

def test_inv43_no_api_schema_accepts_raw_message_content():
    """INV-43: message content reaches the database only through the chained
    append path.

    Asserted on the schema rather than on a request, because the hole this
    closes was a field quietly present on an update model — exactly the kind
    of thing a refactor re-adds without anyone noticing.
    """
    from app.routers.conversations import ConversationUpdate

    assert "messages_json" not in ConversationUpdate.model_fields


def test_inv43_the_delete_route_does_not_destroy_a_transcript():
    """INV-43: the delete button tombstones; it does not erase what was said."""
    import inspect

    from app.routers.conversations import delete_conversation

    src = inspect.getsource(delete_conversation)
    assert "deleted_at" in src, "delete_conversation no longer tombstones"
    assert "db.delete(" not in src, (
        "delete_conversation destroys the conversation row, and its messages "
        "with it through ON DELETE CASCADE"
    )


def test_inv43_every_message_write_goes_through_the_chained_append():
    """INV-43: no module builds a ConversationMessage of its own.

    A second construction site would be a message that never enters the chain.
    The store and the backfill helper are the two places allowed to.
    """
    import pathlib

    allowed = {
        "app/services/conversation_messages.py",
        "app/services/conversation_backfill.py",
    }
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in list((root / "app").rglob("*.py")) + list((root / "packages").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "ConversationMessage(" in text:
            offenders.append(rel)
    assert offenders == [], (
        "INV-43 violated — these construct messages outside the chained "
        "append path:\n" + "\n".join(offenders)
    )


def test_inv43_conversation_chains_do_not_use_the_global_audit_lock():
    """INV-43's performance half: chat writes must not queue on 0xA0D17.

    If the message store ever took the audit advisory lock, every message in
    every conversation would serialise on it — the bottleneck the
    per-conversation chain exists to avoid.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    store = (root / "app/services/conversation_messages.py").read_text()
    assert "0xA0D17" not in store and "advisory" not in store.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_invariants_static.py -q
```

Expected: FAIL only if something is genuinely wrong. If Tasks 3–5 are complete these pass immediately; that is acceptable for an invariant test, whose job is to fail on a *future* regression. To confirm each one bites, temporarily re-add `messages_json: Optional[str] = None` to `ConversationUpdate` and check that `test_inv43_no_api_schema_accepts_raw_message_content` fails, then revert.

- [ ] **Step 3: Document the invariant**

In `docs/delivery/ARCHITECTURE_AND_SECURITY.md`, next to the existing INV-42 paragraph, add:

```markdown
INV-43: the assistant's words are evidence. Every message persisted to a
conversation enters a per-conversation hash chain before it is readable
(`app/services/conversation_chain.py`), no API accepts a message-content write
outside that path, and each conversation's chain head is periodically anchored
into the global audit chain (`app/services/conversation_anchor.py`). The chain
is per conversation rather than global so chat writes never queue on the audit
advisory lock; the anchor is what makes a deleted conversation detectable.
See `docs/superpowers/specs/2026-09-16-chat-message-storage-design.md`.
```

- [ ] **Step 4: Run everything**

```bash
make check
```

Expected: full Python suite + invariants + frontend gates all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_invariants_static.py docs/delivery/ARCHITECTURE_AND_SECURITY.md
git commit -m "$(cat <<'EOF'
test: enforce INV-43, the assistant's words are evidence

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| §2 D1 messages table | 2, 3 |
| §2 D2 per-conversation chain | 1, 3 |
| §2 D3 anchoring | 5 |
| §2 D4 unique `(conversation_id, seq)` | 2 (constraint), 3 (concurrency test) |
| §2 D5 `messages_json` off the update schema | 4 |
| §2 D6 tombstone delete | 2 (column), 4 (route) |
| §2 D7 flagged backfill | 2 |
| §2 D8 legacy column retained | 2 (migration adds, does not drop) |
| §3 schema, §3.1 hash coverage | 1, 2 |
| §4 append path | 3 |
| §4.1 anchoring | 5 |
| §5 read paths | 3 (four of five), 6 (`GlobalSearch`) |
| §6 performance | 3 (§7.6 cost test) |
| §7.1–7.6 testing | 1, 3, 4, 5, 2 respectively |
| §8 not foreclosing Rounds 2/3 | `content` stays plain `TEXT`; `id` is monotonic `BIGSERIAL`; `deleted_at` exists |
| §9 INV-43 | 7 |
