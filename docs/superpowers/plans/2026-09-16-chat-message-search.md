# Chat Message Search (Round 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A server-side endpoint that searches the caller's own chat messages across their whole history, with `GlobalSearch` rewired to use it.

**Architecture:** A `pg_trgm` GIN index on `conversation_messages.content` plus a partial index on the owner narrows the candidate set to one user's live, human-facing conversations; the search is a join with an escaped `ILIKE`, paged on the monotonic message id. Full-text search is not used — PostgreSQL treats a whole Chinese sentence as one lexeme.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16 with `pg_trgm`, pytest/pytest-asyncio, React 18 + TypeScript + vitest.

**Spec:** `docs/superpowers/specs/2026-09-16-chat-message-search-design.md`

## Global Constraints

- Migration revision id must be **≤32 characters** — `alembic_version.version_num` is `varchar(32)`. This plan uses `044_conversation_search` (23 chars), revising `043_drop_dead_security_toggles`.
- **`GET /conversations/search` must be declared BEFORE `GET /conversations/{conv_id}`** (`app/routers/conversations.py:174`). FastAPI matches in declaration order; declared after, `/conversations/search` matches `{conv_id}`, fails `int` parsing and returns 422. This is the single most likely way to get this task wrong.
- `%`, `_` and `\` in a user's query are escaped and the statement uses `ESCAPE '\'`. SQLAlchemy: `.ilike(pattern, escape="\\")`.
- Search excludes conversations where `deleted_at IS NOT NULL` **or** `agent_id IS NOT NULL` (spec D9/§3.1). Both live in the partial index predicate *and* in the query — the index is an optimisation, never the security boundary.
- The search function takes the owner as an explicit parameter and never reads a token itself (spec §7), so a Round 3 auditor path can pass a different scope.
- `pyproject.toml` sets `asyncio_mode = "auto"`; `AsyncSessionLocal` uses `expire_on_commit=False`.
- Tests run against a real PostgreSQL. `make check` tears the test services down on exit via a trap — if `pytest` reports `Connect call failed … 55432`, run `make test-env-up` and `alembic upgrade head` again.
- Commit **only** the files each step names. The tree carries unrelated user WIP (`webui/src/index.css`); never `git add -A` or `git add .`.
- Never pipe pytest into `tail`/`head` before committing — the pipe masks the exit code.

---

### Task 1: The snippet, as a pure function

**Files:**
- Create: `app/services/message_snippet.py`
- Test: `tests/test_message_snippet.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SNIPPET_CHARS: int = 200`
  - `snippet(content: str, term: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_message_snippet.py`:

```python
"""The fragment a search result shows instead of the whole message.

Returning message bodies would let one long transcript dominate a page of
results, and the pane only renders a single preview line. Centring on the hit
is what makes the result readable: a match 4000 characters into an answer is
useless if the snippet starts at character zero.
"""
from __future__ import annotations

from app.services.message_snippet import SNIPPET_CHARS, snippet


def test_a_short_message_is_returned_whole():
    assert snippet("three open ports", "ports") == "three open ports"


def test_a_short_message_gains_no_ellipsis():
    assert "…" not in snippet("three open ports", "ports")


def test_the_snippet_is_centred_on_the_hit():
    content = ("a" * 1000) + "NEEDLE" + ("b" * 1000)
    out = snippet(content, "needle")
    assert "NEEDLE" in out
    assert len(out) <= SNIPPET_CHARS + 2  # plus the two ellipses
    assert out.startswith("…") and out.endswith("…")


def test_a_hit_near_the_start_does_not_pad_the_left():
    content = "NEEDLE" + ("b" * 1000)
    out = snippet(content, "needle")
    assert out.startswith("NEEDLE"), "no leading ellipsis when nothing was cut"
    assert out.endswith("…")


def test_a_hit_near_the_end_does_not_pad_the_right():
    content = ("a" * 1000) + "NEEDLE"
    out = snippet(content, "needle")
    assert out.startswith("…")
    assert out.endswith("NEEDLE")


def test_matching_ignores_case():
    assert "Ports" in snippet("three open Ports here", "PORTS")


def test_chinese_content_is_measured_in_characters_not_bytes():
    """A CJK character is three bytes in UTF-8; slicing by bytes would cut one
    in half and produce mojibake."""
    content = ("甲" * 500) + "开放端口" + ("乙" * 500)
    out = snippet(content, "开放端口")
    assert "开放端口" in out
    assert len(out) <= SNIPPET_CHARS + 2


def test_no_hit_falls_back_to_the_opening(): 
    """Only reachable if the row changed between matching and reading. A
    snippet is not worth raising over."""
    out = snippet("a" * 1000, "nothing here")
    assert out.startswith("a")
    assert len(out) <= SNIPPET_CHARS + 1


def test_an_empty_term_does_not_raise():
    assert isinstance(snippet("some content", ""), str)


def test_empty_content_is_empty():
    assert snippet("", "anything") == ""
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/jc/Documents/Claude/Projects/cyber-agent/cyberguard
python -m pytest tests/test_message_snippet.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.message_snippet'`.

- [ ] **Step 3: Write the implementation**

Create `app/services/message_snippet.py`:

```python
"""The fragment a search result shows in place of the message body.

Search results carry a snippet rather than the message, because one long
transcript would otherwise dominate a page of results and the pane renders a
single preview line anyway.

Pure and DB-free, like ``app.core.audit_diff`` and
``app.services.conversation_chain``.
"""
from __future__ import annotations

SNIPPET_CHARS = 200
_ELLIPSIS = "…"


def snippet(content: str, term: str) -> str:
    """At most ``SNIPPET_CHARS`` characters of ``content``, centred on ``term``.

    Sliced by character, not byte: a CJK character is three bytes in UTF-8 and
    a byte slice would cut one in half.
    """
    if not content:
        return ""
    if len(content) <= SNIPPET_CHARS:
        return content

    index = content.lower().find(term.lower()) if term else -1
    if index < 0:
        # Only reachable if the row changed between matching and reading. The
        # opening of the message is more useful than an error.
        return content[:SNIPPET_CHARS] + _ELLIPSIS

    half = (SNIPPET_CHARS - len(term)) // 2
    start = max(0, index - half)
    end = min(len(content), start + SNIPPET_CHARS)
    # Re-extend leftwards when the hit sits near the end, so the window stays
    # the full width instead of trailing off short.
    start = max(0, end - SNIPPET_CHARS)

    out = content[start:end]
    if start > 0:
        out = _ELLIPSIS + out
    if end < len(content):
        out = out + _ELLIPSIS
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_message_snippet.py -q
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/message_snippet.py tests/test_message_snippet.py
git commit -m "$(cat <<'EOF'
feat: add the search-result snippet

Centred on the hit and sliced by character: a match 4000 characters into an
answer is useless if the snippet starts at zero, and a byte slice would cut a
CJK character in half.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: The indexes

**Files:**
- Create: `alembic/versions/044_conversation_search.py`
- Test: `tests/test_conversation_search_indexes.py`

**Interfaces:**
- Consumes: the `conversation_messages` table and `conversations.deleted_at` (Round 1).
- Produces: extension `pg_trgm`; indexes `ix_conv_user_live`, `ix_conv_messages_content_trgm`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_search_indexes.py`:

```python
"""The indexes search depends on, asserted against the real database.

Round 1's spec planned a tsvector column. Measured, PostgreSQL tokenises a
whole Chinese sentence as one lexeme — `to_tsvector('english', '扫描主机的开放
端口')` is a single term, and searching 端口 does not match it. These tests pin
the pg_trgm arrangement that replaced it, including the property that made the
partial index worth having.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def _scalar(sql: str):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql))).scalar()


@pytest.mark.asyncio
async def test_pg_trgm_is_installed():
    assert await _scalar("SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'") == 1


@pytest.mark.asyncio
async def test_the_content_index_is_a_trigram_gin_index():
    definition = await _scalar(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname='ix_conv_messages_content_trgm'")
    assert definition is not None, "the content index is missing"
    assert "USING gin" in definition
    assert "gin_trgm_ops" in definition


@pytest.mark.asyncio
async def test_the_owner_index_excludes_tombstones_and_agent_slices():
    """The predicate is the point: a deleted or agent-internal conversation is
    absent from the index rather than filtered out by each query that
    remembers to."""
    definition = await _scalar(
        "SELECT indexdef FROM pg_indexes WHERE indexname='ix_conv_user_live'")
    assert definition is not None, "the owner index is missing"
    assert "WHERE" in definition
    assert "deleted_at IS NULL" in definition
    assert "agent_id IS NULL" in definition


@pytest.mark.asyncio
async def test_full_text_search_would_not_have_worked_for_chinese():
    """Kept as a regression guard on the decision, not on our code: if someone
    later proposes tsvector again, this is the measurement that says no."""
    matched = await _scalar(
        "SELECT to_tsvector('simple', '扫描主机的开放端口') "
        "@@ plainto_tsquery('simple', '端口')")
    assert matched is False, (
        "PostgreSQL now segments Chinese — revisit the search design, because "
        "full-text search would be better than trigram matching")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_search_indexes.py -q
```

Expected: FAIL — `pg_trgm` is not installed and both indexes are missing.

- [ ] **Step 3: Write the migration**

Create `alembic/versions/044_conversation_search.py`:

```python
"""Indexes for user-scoped chat message search.

Round 1 planned a tsvector column. PostgreSQL tokenises a whole Chinese
sentence as one lexeme and zhparser is not in the image, so full-text search
cannot match a keyword inside Chinese content. pg_trgm can.

The owner index is partial. A tombstoned conversation and an internal agent's
memory slice are both rows a person owns and neither belongs in their search
results, so they are absent from the index rather than filtered out by every
query that remembers to.

Revision ID: 044_conversation_search  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 043_drop_dead_security_toggles
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "044_conversation_search"
down_revision: Union[str, None] = "043_drop_dead_security_toggles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # conversations.user_id had no index at all, so this also makes the
    # existing list_conversations cheaper.
    op.create_index(
        "ix_conv_user_live", "conversations", ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL AND agent_id IS NULL"),
    )
    op.create_index(
        "ix_conv_messages_content_trgm", "conversation_messages", ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_conv_messages_content_trgm", table_name="conversation_messages")
    op.drop_index("ix_conv_user_live", table_name="conversations")
    # The extension is left installed: another table may have come to depend on
    # it, and dropping it would take those indexes with it.
```

- [ ] **Step 4: Apply it and run the test**

```bash
make test-env-up
DATABASE_URL="postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test" \
REDIS_URL="redis://:cyberguard-test-only@localhost:56379/0" REDIS_PASSWORD=cyberguard-test-only \
ENCRYPTION_KEY=1111111111111111111111111111111111111111111111111111111111111111 \
SECRET_KEY=2222222222222222222222222222222222222222222222222222222222222222 \
ENVIRONMENT=testing AUTO_APPROVE=false PYTHONPATH="packages:$PWD" \
  .venv/bin/alembic -c alembic.ini upgrade head
python -m pytest tests/test_conversation_search_indexes.py tests/test_alembic_startup.py -q
```

Expected: migration applies; all pass.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/044_conversation_search.py \
        tests/test_conversation_search_indexes.py
git commit -m "$(cat <<'EOF'
feat: index chat messages for user-scoped search

pg_trgm rather than tsvector: PostgreSQL tokenises a whole Chinese sentence as
one lexeme, so full-text search cannot match a keyword inside it.

The owner index is partial on deleted_at IS NULL AND agent_id IS NULL, so a
tombstoned conversation and an agent's memory slice are absent from it rather
than filtered out by each query.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: The search query and the endpoint

**Files:**
- Create: `app/services/message_search.py`
- Modify: `app/routers/conversations.py` — the new route goes **immediately before** `@router.get("/conversations/{conv_id}")` at line 174
- Test: `tests/test_conversation_search.py`

**Interfaces:**
- Consumes: `snippet`, `SNIPPET_CHARS` (Task 1); the indexes (Task 2).
- Produces, in `app.services.message_search`:
  - `DEFAULT_SEARCH_LIMIT: int = 20`, `MAX_SEARCH_LIMIT: int = 100`
  - `escape_like(term: str) -> str`
  - `SearchHit` — a frozen dataclass with `conversation_id: int`, `conversation_title: Optional[str]`, `message_id: int`, `seq: int`, `role: str`, `content: str`, `created_at: datetime`
  - `async search_messages(session: AsyncSession, *, user_id: int, term: str, limit: int = DEFAULT_SEARCH_LIMIT, cursor: Optional[int] = None) -> List[SearchHit]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_conversation_search.py`:

```python
"""Searching your own chat history.

The permission boundary is the test that matters most here: a search that can
reach another user's messages is a data breach, not a bug. It is asserted
against two seeded users rather than by reading the code.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_messages import append_messages_locked
from app.services.message_search import escape_like, search_messages


@pytest.fixture
async def world():
    """Two users. Amy has an ordinary conversation, a deleted one, and an
    internal agent's memory slice. Bob has one conversation of his own."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        amy = User(username=f"amy_{suffix}", email=f"amy_{suffix}@company.local",
                   hashed_password="test-only", role="admin", is_active=True)
        bob = User(username=f"bob_{suffix}", email=f"bob_{suffix}@company.local",
                   hashed_password="test-only", role="admin", is_active=True)
        db.add_all([amy, bob])
        await db.flush()

        live = Conversation(user_id=amy.id, title="Port scan triage")
        gone = Conversation(user_id=amy.id, title="Deleted work")
        slice_ = Conversation(user_id=amy.id, title="agent:recon")
        bobs = Conversation(user_id=bob.id, title="Bob's own")
        db.add_all([live, gone, slice_, bobs])
        await db.flush()

        # agent_id is what makes a row an internal agent's memory rather than a
        # conversation. It is a foreign key, so the slice needs a real agent.
        # agent_name and backend_type are AgentConfig's only required columns.
        agent = AgentConfig(agent_name=f"recon_{suffix}", backend_type="__internal__")
        db.add(agent)
        await db.flush()
        slice_.agent_id = agent.id
        slice_.parent_conversation_id = live.id
        await db.commit()

        await append_messages_locked(db, live.id, [
            {"role": "user", "content": "扫描主机的开放端口"},
            {"role": "assistant", "content": "three open ports, including 22/tcp"},
            {"role": "assistant", "content": "utilisation reached 100% briefly"},
            {"role": "user", "content": "check a_b naming"},
        ])
        await append_messages_locked(db, gone.id, [
            {"role": "user", "content": "端口 in a conversation that gets deleted"}])
        await append_messages_locked(db, bobs.id, [
            {"role": "user", "content": "端口 belonging to Bob"}])
        await append_messages_locked(db, slice_.id, [
            {"role": "assistant", "content": "端口 internal agent reasoning"}])
        await db.commit()

        ids = dict(amy=amy.id, bob=bob.id, live=live.id, gone=gone.id,
                   slice=slice_.id, bobs=bobs.id, agent=agent.id)
    yield ids
    async with AsyncSessionLocal() as db:
        for cid in (ids["live"], ids["gone"], ids["slice"], ids["bobs"]):
            await db.execute(ConversationMessage.__table__.delete().where(
                ConversationMessage.conversation_id == cid))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id.in_([ids["amy"], ids["bob"]])))
        await db.execute(User.__table__.delete().where(
            User.id.in_([ids["amy"], ids["bob"]])))
        await db.execute(AgentConfig.__table__.delete().where(
            AgentConfig.id == ids["agent"]))
        await db.commit()


async def _search(user_id, term, **kw):
    async with AsyncSessionLocal() as db:
        return await search_messages(db, user_id=user_id, term=term, **kw)


# --- correctness ---

@pytest.mark.asyncio
async def test_an_english_term_finds_its_message(world):
    hits = await _search(world["amy"], "open ports")
    assert [h.content for h in hits] == ["three open ports, including 22/tcp"]


@pytest.mark.asyncio
async def test_a_two_character_chinese_term_finds_its_message(world):
    """The case the trigram index cannot accelerate. It must still be correct —
    the index is a speed decision, never a correctness one."""
    hits = await _search(world["amy"], "端口")
    assert any("开放端口" in h.content for h in hits)


@pytest.mark.asyncio
async def test_results_carry_the_conversation_they_belong_to(world):
    hits = await _search(world["amy"], "open ports")
    assert hits[0].conversation_id == world["live"]
    assert hits[0].conversation_title == "Port scan triage"


# --- the permission boundary ---

@pytest.mark.asyncio
async def test_a_search_never_reaches_another_users_messages(world):
    """The one that matters. Bob's message contains the term; Amy must not see it."""
    hits = await _search(world["amy"], "端口")
    assert all(h.conversation_id != world["bobs"] for h in hits)
    assert all("Bob" not in h.content for h in hits)


@pytest.mark.asyncio
async def test_each_user_sees_only_their_own(world):
    bob_hits = await _search(world["bob"], "端口")
    assert len(bob_hits) == 1
    assert bob_hits[0].conversation_id == world["bobs"]


# --- tombstones ---

@pytest.mark.asyncio
async def test_a_deleted_conversations_messages_are_not_returned(world):
    from app.core.time import utc_now

    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, world["gone"])
        conv.deleted_at = utc_now()
        await db.commit()

    hits = await _search(world["amy"], "端口")
    assert all(h.conversation_id != world["gone"] for h in hits)

    async with AsyncSessionLocal() as db:
        surviving = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == world["gone"]))).scalars().all()
    assert len(surviving) == 1, "Round 1's immutability must not be weakened"


# --- escaping ---

def test_escape_like_neutralises_wildcards():
    assert escape_like("100%") == r"100\%"
    assert escape_like("a_b") == r"a\_b"
    assert escape_like(r"back\slash") == r"back\\slash"


@pytest.mark.asyncio
async def test_a_percent_sign_is_a_literal_not_a_wildcard(world):
    hits = await _search(world["amy"], "100%")
    assert len(hits) == 1
    assert "100%" in hits[0].content


@pytest.mark.asyncio
async def test_an_underscore_is_a_literal_not_a_single_character_wildcard(world):
    assert len(await _search(world["amy"], "a_b")) == 1
    assert await _search(world["amy"], "axb") == []


# --- paging ---

@pytest.mark.asyncio
async def test_paging_returns_each_hit_once(world):
    first = await _search(world["amy"], "e", limit=2)
    assert len(first) == 2
    second = await _search(world["amy"], "e", limit=2, cursor=first[-1].message_id)
    ids = [h.message_id for h in first] + [h.message_id for h in second]
    assert len(ids) == len(set(ids)), "a message appeared on two pages"


@pytest.mark.asyncio
async def test_results_are_newest_first(world):
    hits = await _search(world["amy"], "e", limit=10)
    assert [h.message_id for h in hits] == sorted(
        (h.message_id for h in hits), reverse=True)


@pytest.mark.asyncio
async def test_the_limit_is_capped(world):
    from app.services.message_search import MAX_SEARCH_LIMIT

    hits = await _search(world["amy"], "e", limit=10_000)
    assert len(hits) <= MAX_SEARCH_LIMIT


@pytest.mark.asyncio
async def test_an_agent_memory_slice_is_never_searched(world):
    """The slice is a conversations row owned by the searching user, holding an
    internal agent's working memory. Searching your chat history means the
    conversations you had."""
    hits = await _search(world["amy"], "端口")
    assert all(h.conversation_id != world["slice"] for h in hits)


# --- the endpoint ---

@pytest.mark.asyncio
async def test_the_endpoint_returns_snippets_not_message_bodies(world):
    from app.routers.conversations import search_conversation_messages

    amy = AuthenticatedUser(user_id=world["amy"], username="amy",
                            email="amy@company.local", role="admin")
    async with AsyncSessionLocal() as db:
        payload = await search_conversation_messages("open ports", 20, None, db, amy)

    assert payload["results"], "expected a hit"
    assert set(payload["results"][0]) == {
        "conversation_id", "conversation_title", "message_id", "seq", "role",
        "created_at", "snippet"}


@pytest.mark.asyncio
async def test_an_empty_query_is_rejected(world):
    from fastapi import HTTPException

    from app.routers.conversations import search_conversation_messages

    amy = AuthenticatedUser(user_id=world["amy"], username="amy",
                            email="amy@company.local", role="admin")
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await search_conversation_messages("   ", 20, None, db, amy)
    assert exc.value.status_code == 400


def test_the_search_route_is_declared_before_the_conversation_id_route():
    """FastAPI matches in declaration order. Declared after, /conversations/
    search binds to {conv_id}, fails int parsing and 422s — with no test
    failing anywhere else to explain why."""
    import inspect

    from app.routers import conversations as module

    src = inspect.getsource(module)
    assert src.index('"/conversations/search"') < src.index('"/conversations/{conv_id}"')


def test_the_endpoint_takes_the_user_from_the_token_only():
    """A user_id parameter would make this an admin endpoint wearing a
    self-service name."""
    import inspect

    from app.routers.conversations import search_conversation_messages

    assert "user_id" not in inspect.signature(search_conversation_messages).parameters
    assert "current_user.user_id" in inspect.getsource(search_conversation_messages)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_search.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.message_search'`.

- [ ] **Step 3: Write the search service**

Create `app/services/message_search.py`:

```python
"""Keyword search over chat messages, scoped to one owner.

Matching is ``ILIKE`` over a ``pg_trgm`` index rather than full-text search:
PostgreSQL tokenises a whole Chinese sentence as one lexeme, so a tsvector
cannot match a keyword inside one (see the Round 2 design).

``user_id`` is a parameter rather than something this module reads from a
token, so the Round 3 auditor path can pass a different scope without the
search being rewritten. The caller is responsible for deciding whose messages
these are; this module is responsible for honouring that decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100

_LIKE_ESCAPE = "\\"


@dataclass(frozen=True)
class SearchHit:
    conversation_id: int
    conversation_title: Optional[str]
    message_id: int
    seq: int
    role: str
    content: str
    created_at: datetime


def escape_like(term: str) -> str:
    """Neutralise LIKE wildcards in a user's query.

    Without this, searching ``100%`` matches every message and ``a_b`` matches
    ``axb``. The backslash goes first, or it would escape the escapes.
    """
    return (
        term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


async def search_messages(
    session: AsyncSession,
    *,
    user_id: int,
    term: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    cursor: Optional[int] = None,
) -> List[SearchHit]:
    """Messages owned by ``user_id`` containing ``term``, newest first.

    Excludes tombstoned conversations and internal-agent memory slices. Those
    predicates are repeated here rather than left to the partial index: the
    index is an optimisation and must never be the security boundary.
    """
    pattern = f"%{escape_like(term)}%"
    stmt = (
        select(
            ConversationMessage.conversation_id,
            Conversation.title,
            ConversationMessage.id,
            ConversationMessage.seq,
            ConversationMessage.role,
            ConversationMessage.content,
            ConversationMessage.created_at,
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
            Conversation.agent_id.is_(None),
            ConversationMessage.content.ilike(pattern, escape=_LIKE_ESCAPE),
        )
        .order_by(ConversationMessage.id.desc())
        .limit(max(1, min(int(limit), MAX_SEARCH_LIMIT)))
    )
    if cursor is not None:
        stmt = stmt.where(ConversationMessage.id < cursor)

    rows = (await session.execute(stmt)).all()
    return [
        SearchHit(
            conversation_id=row[0], conversation_title=row[1], message_id=row[2],
            seq=row[3], role=row[4], content=row[5], created_at=row[6],
        )
        for row in rows
    ]
```

- [ ] **Step 4: Add the endpoint, before the `{conv_id}` route**

In `app/routers/conversations.py`, add to the imports:

```python
from app.services.message_search import (
    DEFAULT_SEARCH_LIMIT,
    search_messages,
)
from app.services.message_snippet import snippet
```

Insert this **immediately above** `@router.get("/conversations/{conv_id}", response_model=ConversationResponse)` — see the Global Constraints; placed after it, the path binds to `{conv_id}` and 422s:

```python
# Declared before /conversations/{conv_id}: FastAPI matches in declaration
# order, and "search" would otherwise bind to conv_id and fail int parsing.
@router.get("/conversations/search")
async def search_conversation_messages(
    q: str = "",
    limit: int = DEFAULT_SEARCH_LIMIT,
    cursor: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Search your own chat messages.

    The owner comes from the token and is never accepted as a parameter; a
    user_id here would make this an admin endpoint wearing a self-service name.
    """
    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="q is required")

    hits = await search_messages(
        db, user_id=current_user.user_id, term=term, limit=limit, cursor=cursor)

    return {
        "results": [
            {
                "conversation_id": hit.conversation_id,
                "conversation_title": hit.conversation_title,
                "message_id": hit.message_id,
                "seq": hit.seq,
                "role": hit.role,
                "created_at": hit.created_at.isoformat() if hit.created_at else None,
                "snippet": snippet(hit.content, term),
            }
            for hit in hits
        ],
        "next_cursor": hits[-1].message_id if hits else None,
    }
```

- [ ] **Step 5: Run the tests**

```bash
python -m pytest tests/test_conversation_search.py -q
```

Expected: all pass.

- [ ] **Step 6: Verify the index is actually used**

Not a unit test — a one-off check that the arrangement works, since an index
nothing uses is worth knowing about:

```bash
docker compose -p cyberguard-preview exec -T postgres psql -U postgres -d cyberguard -c "
EXPLAIN SELECT m.id FROM conversation_messages m
JOIN conversations c ON c.id = m.conversation_id
WHERE c.user_id = 1 AND c.deleted_at IS NULL AND c.agent_id IS NULL
  AND m.content ILIKE '%firewall%' ORDER BY m.id DESC LIMIT 20;"
```

Expected: the plan references `ix_conv_user_live` or
`ix_conv_messages_content_trgm`. On a nearly empty table PostgreSQL may still
choose a sequential scan, which is correct — record what you saw and move on.

- [ ] **Step 7: Commit**

```bash
git add app/services/message_search.py app/routers/conversations.py \
        tests/test_conversation_search.py
git commit -m "$(cat <<'EOF'
feat: search your own chat messages

ILIKE over a pg_trgm index rather than full-text search, which cannot match a
keyword inside Chinese content. The owner comes from the token and is never a
parameter, and the tombstone and agent-slice predicates are repeated in the
query rather than left to the partial index — an index is an optimisation,
never the security boundary.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Stop listing internal-agent memory as conversations

Spec §3.1. Small, but it is a user-visible leak in its own right and a reviewer could reasonably accept it while rejecting the search work, so it stands alone.

**Files:**
- Modify: `app/routers/conversations.py` — `list_conversations`
- Test: `tests/test_conversation_immutability.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_conversation_immutability.py`:

```python
@pytest.mark.asyncio
async def test_agent_memory_slices_are_not_listed_as_conversations(seeded):
    """InternalAgentRunner stores each agent's memory as a conversations row
    owned by the person, titled `agent:<name>`. list_conversations filtered
    only on user_id and deleted_at, so those slices belonged in the sidebar —
    unnoticed only because no deployment had run an internal agent yet.
    """
    from app.models.agent import AgentConfig

    _, user_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        agent = AgentConfig(agent_name=f"recon_{uuid.uuid4().hex[:8]}",
                            backend_type="__internal__")
        db.add(agent)
        await db.flush()
        slice_ = Conversation(user_id=user_id, title="agent:recon",
                              agent_id=agent.id)
        db.add(slice_)
        await db.commit()
        agent_id, slice_id = agent.id, slice_.id

        try:
            listed = await list_conversations(db, _user(seeded))
            assert all(c.id != slice_id for c in listed), (
                "an internal agent's memory is showing as a conversation")
        finally:
            await db.execute(Conversation.__table__.delete().where(
                Conversation.id == slice_id))
            await db.execute(AgentConfig.__table__.delete().where(
                AgentConfig.id == agent_id))
            await db.commit()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_conversation_immutability.py -q -k agent_memory
```

Expected: FAIL — the slice appears in the listing.

- [ ] **Step 3: Add the filter**

In `list_conversations`, add one predicate to the existing `where`:

```python
        .where(
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
            # An internal agent's memory is stored as a conversations row owned
            # by the person (internal_agent.py:181). It is not a conversation
            # they had.
            Conversation.agent_id.is_(None),
        )
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_conversation_immutability.py tests/test_conversation_search.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/routers/conversations.py tests/test_conversation_immutability.py
git commit -m "$(cat <<'EOF'
fix: stop listing an agent's memory as one of your conversations

InternalAgentRunner stores each internal agent's working memory as a
conversations row owned by the person, titled agent:<name>.
list_conversations filtered only on user_id and deleted_at, so those rows
belonged in the sidebar — unnoticed only because no deployment had run an
internal agent yet.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Wire the search pane to the server

**Files:**
- Modify: `webui/src/api/client.ts`
- Modify: `webui/src/components/GlobalSearch.tsx`
- Test: `webui/src/components/GlobalSearch.messages.test.tsx`

**Interfaces:**
- Consumes: `GET /conversations/search` (Task 3).
- Produces: `api.searchConversationMessages(q, limit?)`.

- [ ] **Step 1: Write the failing test**

Create `webui/src/components/GlobalSearch.messages.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import GlobalSearch from './GlobalSearch'

/**
 * Round 1 removed message search: the transcript stopped being shipped with
 * the conversation list, so the pane could only match titles. This restores it
 * and goes further — the browser version only ever searched the 50 most recent
 * conversations, and only what was already in memory.
 */
describe('GlobalSearch — message hits', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    for (const name of [
      'getAgents', 'getProviders', 'getSkills', 'getTools', 'getKnowledgeBases',
      'getMCPServers', 'getPromptTemplates', 'getConversations',
    ] as const) {
      vi.spyOn(api, name).mockResolvedValue([] as never)
    }
    vi.spyOn(api, 'searchConversationMessages').mockResolvedValue({
      results: [{
        conversation_id: 7, conversation_title: 'Port scan triage',
        message_id: 91, seq: 3, role: 'assistant',
        created_at: '2026-09-16T10:00:00', snippet: '…three open ports…',
      }],
      next_cursor: 91,
    } as never)
  })

  const type = async (text: string) => {
    render(<GlobalSearch open onClose={() => {}} setTab={() => {}} recentTabs={[]} />)
    const input = await screen.findByPlaceholderText(/SEARCH AGENTS/i)
    fireEvent.change(input, { target: { value: text } })
  }

  it('asks the server for message hits', async () => {
    await type('ports')
    await vi.advanceTimersByTimeAsync(400)
    await waitFor(() =>
      expect(api.searchConversationMessages).toHaveBeenCalledWith('ports'))
  })

  it('shows the snippet the server returned', async () => {
    await type('ports')
    await vi.advanceTimersByTimeAsync(400)
    expect(await screen.findByText(/three open ports/)).toBeTruthy()
  })

  it('debounces a burst of typing into one request', async () => {
    await type('p')
    const input = screen.getByPlaceholderText(/SEARCH AGENTS/i)
    for (const value of ['po', 'por', 'port', 'ports']) {
      fireEvent.change(input, { target: { value } })
    }
    await vi.advanceTimersByTimeAsync(400)
    await waitFor(() =>
      expect(api.searchConversationMessages).toHaveBeenCalledTimes(1))
  })

  it('does not search on an empty query', async () => {
    await type('')
    await vi.advanceTimersByTimeAsync(400)
    expect(api.searchConversationMessages).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd webui && npx vitest run src/components/GlobalSearch.messages.test.tsx
```

Expected: FAIL — `api.searchConversationMessages` does not exist, so `vi.spyOn` throws.

- [ ] **Step 3: Add the API method**

In `webui/src/api/client.ts`, next to `getConversations`:

```typescript
  searchConversationMessages: (q: string, limit?: number) =>
    request(`/conversations/search?q=${encodeURIComponent(q)}` +
            (limit ? `&limit=${limit}` : '')),
```

- [ ] **Step 4: Wire the pane**

In `webui/src/components/GlobalSearch.tsx`, add state beside the existing hooks:

```tsx
  const [messageHits, setMessageHits] = useState<SearchItem[]>([])
```

Add the debounced lookup after the existing catalog `useEffect`:

```tsx
  // Message search runs on the server: the conversation list no longer carries
  // transcripts, and the browser only ever held the 50 most recent anyway.
  useEffect(() => {
    const term = query.trim()
    if (!open || !term) { setMessageHits([]); return }

    let cancelled = false
    const timer = setTimeout(() => {
      void api.searchConversationMessages(term)
        .then(res => {
          if (cancelled) return
          const rows = (res as { results?: Array<{
            conversation_id: number; conversation_title?: string | null
            message_id: number; snippet?: string
          }> }).results || []
          setMessageHits(rows.map(r => ({
            id: `msg-${r.message_id}`,
            name: r.conversation_title || `Conversation #${r.conversation_id}`,
            subtitle: 'MESSAGE',
            tab: 'chat' as Tab,
            category: 'CONVERSATIONS',
            icon: '◉',
            preview: r.snippet || '',
          })))
        })
        .catch(() => { if (!cancelled) setMessageHits([]) })
    }, 250)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [query, open])
```

Then include them in the filtered set. Replace

```tsx
  const filtered = q
    ? allItems.filter(item => {
```

with

```tsx
  // Server-side message hits are already matched; only the catalog needs
  // filtering. Titles still match locally, so a title hit needs no round trip.
  const filtered = q
    ? [...messageHits, ...allItems].filter(item => {
        if (item.id.toString().startsWith('msg-')) return true
```

leaving the rest of the predicate unchanged.

- [ ] **Step 5: Run the frontend gates**

```bash
cd webui && npx vitest run
cd webui && npx tsc --noEmit -p tsconfig.app.json && npx tsc --noEmit -p tsconfig.test.json
```

Expected: all tests pass, both typecheck targets clean.

If `Tab` is not already imported in `GlobalSearch.tsx`, import it from wherever
`Props` gets it rather than widening the type to `string`.

- [ ] **Step 6: Run everything**

```bash
cd /Users/jc/Documents/Claude/Projects/cyber-agent/cyberguard && make check
```

Expected: full Python suite + invariants + frontend gates green.

- [ ] **Step 7: Commit**

```bash
git add webui/src/api/client.ts webui/src/components/GlobalSearch.tsx \
        webui/src/components/GlobalSearch.messages.test.tsx
git commit -m "$(cat <<'EOF'
feat: search message contents from the search pane again

Round 1 removed this when the transcript stopped being shipped with the
conversation list. It now covers the whole history rather than whatever the
browser happened to be holding for the 50 most recent conversations.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| §1 pg_trgm over tsvector | 2 (index), 2 Step 1 (regression guard on the measurement) |
| §2 D1 ILIKE + trigram | 3 |
| §2 D2 partial owner index | 2 |
| §2 D3 no denormalised user_id | 3 (join in `search_messages`) |
| §2 D4 no composite GIN | 2 (two separate indexes) |
| §2 D5 owner from token only | 3 (endpoint + source-level test) |
| §2 D6 escaping | 3 (`escape_like` + three tests) |
| §2 D7 snippet not body | 1, 3 |
| §2 D8 cursor paging | 3 |
| §2 D9 agent slices excluded | 2 (index), 3 (query + test), 4 (listing) |
| §3 schema, §3.1 listing bug | 2, 4 |
| §4 endpoint shape, §4.1 snippet | 3, 1 |
| §5 frontend | 5 |
| §6 testing | 1, 3, 4, 5 |
| §7 not foreclosing Round 3 | 3 (`user_id` is a parameter, not read from a token) |
| §8 the stated limit | 3 (the two-character Chinese test asserts correctness, not speed) |
