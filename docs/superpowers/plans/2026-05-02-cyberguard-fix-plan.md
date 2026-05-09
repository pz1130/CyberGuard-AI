# CyberGuard Fix & Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all broken functionality in CyberGuard: 7 critical bugs, SSE streaming chat, pgvector knowledge search, and update architecture docs.

**Architecture:** Docker Compose (FastAPI + PostgreSQL/pgvector + Redis + Celery). Chat dispatches via Celery, Worker publishes LLM stream deltas to Redis pub/sub channel `task:{id}`, FastAPI SSE endpoint subscribes and pushes to browser via `EventSource`. Knowledge uses pgvector HNSW for semantic search.

**Tech Stack:** FastAPI, SQLAlchemy 2, asyncpg, pgvector 0.2+, Redis pub/sub, Celery, LangGraph, React/TypeScript, EventSource API

**Reference:** Reuse patterns from https://github.com/agentscope-ai/QwenPaw for streaming and knowledge implementations where applicable.

**Spec:** `docs/superpowers/specs/2026-05-02-cyberguard-fix-design.md`

---

## File Map

| File | Action |
|------|--------|
| `docker-compose.yml` | Modify — postgres image |
| `app/config.py` | Modify — dev-mode key validation |
| `alembic/versions/002_vector_chunks.py` | Create — pgvector migration |
| `migrations/versions/add_vector_chunks.py` | Delete — wrong directory, replaced above |
| `app/models/knowledge.py` | Modify — Vector type for embedding column |
| `app/workers/tasks.py` | Modify — normalize output_data |
| `app/agents/master.py` | Modify — pass execution_id through state |
| `app/services/llm_router.py` | Modify — streaming chat with Redis publish |
| `app/routers/chat.py` | Modify — add SSE stream endpoint |
| `app/routers/tasks.py` | Modify — add /tasks/stats endpoint |
| `app/routers/config.py` | Modify — add GET/PATCH /config/settings |
| `webui/src/pages/Chat.tsx` | Modify — replace polling with EventSource |
| `webui/src/pages/Schedule.tsx` | Modify — cron → cron_expression |
| `webui/src/pages/GroupChat.tsx` | Modify — add ?token= to WS URL |
| `webui/src/pages/Security.tsx` | Modify — connect toggles to backend |
| `webui/src/pages/Providers.tsx` | Modify — dynamic routing table |
| `webui/src/pages/TokenUsage.tsx` | Modify — connect to /tasks/stats |
| `webui/src/api/client.ts` | Modify — add new API methods |
| `01_System_Design_Document_EN.md` | Modify — architecture update |
| `02_SUB_AGENTS.md` | Modify — streaming update |
| `03_MASTER_AGENT.md` | Modify — execution_id + SSE |
| `04_API_AND_BACKEND.md` | Modify — new endpoints |
| `05_WEBUI_DESIGN.md` | Modify — EventSource chat |
| `06_DEPLOYMENT_AND_SECURITY.md` | Modify — pgvector + dev keys |
| `07_IMPLEMENTATION_ROADMAP.md` | Modify — updated roadmap |

---

### Task 1: Switch postgres image to pgvector

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Update postgres image**

In `docker-compose.yml`, change line 3:

```yaml
# Before
    image: postgres:16-alpine

# After
    image: pgvector/pgvector:pg16
```

The full postgres service block becomes:
```yaml
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: cyberguard
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 2: Verify image exists**

```bash
docker pull pgvector/pgvector:pg16
```

Expected: image pulled without error.

- [ ] **Step 3: Commit**

```bash
cd cyberguard
git add docker-compose.yml
git commit -m "fix: use pgvector/pgvector:pg16 postgres image"
```

---

### Task 2: Fix config.py dev-mode startup failure

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import pytest
import os


def test_dev_mode_allows_default_keys(monkeypatch):
    """Dev mode must not raise on default keys."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    # Re-import to pick up patched env
    import importlib
    import app.config as cfg
    importlib.reload(cfg)
    # Should not raise
    settings = cfg.Settings(ENVIRONMENT="development")
    assert settings.ENVIRONMENT == "development"


def test_prod_mode_rejects_default_keys():
    """Production mode must raise on default keys."""
    from app.config import DEFAULT_KEY
    import pytest
    from pydantic import ValidationError
    with pytest.raises((ValueError, ValidationError)):
        from app.config import Settings
        Settings(ENVIRONMENT="production", ENCRYPTION_KEY=DEFAULT_KEY, SECRET_KEY=DEFAULT_KEY)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cyberguard
python -m pytest tests/test_config.py -v
```

Expected: `test_dev_mode_allows_default_keys` FAILS with ValidationError.

- [ ] **Step 3: Implement fix in app/config.py**

Find the `validate_security_keys` method (around line 55) and replace:

```python
# Before
@model_validator(mode="after")
def validate_security_keys(self) -> "Settings":
    """Ensure ENCRYPTION_KEY and SECRET_KEY are not using default values."""
    if self.ENCRYPTION_KEY == DEFAULT_KEY or self.SECRET_KEY == DEFAULT_KEY:
        raise ValueError(
            "ENCRYPTION_KEY and SECRET_KEY must be configured with unique values. "
            "Do not use the default insecure key in production. "
            "Set the CYBERGUARD_ENCRYPTION_KEY and CYBERGUARD_SECRET_KEY environment variables."
        )
    return self
```

```python
# After
@model_validator(mode="after")
def validate_security_keys(self) -> "Settings":
    """Ensure ENCRYPTION_KEY and SECRET_KEY are not using default values."""
    if self.ENCRYPTION_KEY == DEFAULT_KEY or self.SECRET_KEY == DEFAULT_KEY:
        if self.ENVIRONMENT != "development":
            raise ValueError(
                "ENCRYPTION_KEY and SECRET_KEY must be configured with unique values. "
                "Do not use the default insecure key in production."
            )
        import logging
        logging.getLogger(__name__).warning(
            "[config] Using default insecure keys — OK for local development only. "
            "Set ENCRYPTION_KEY and SECRET_KEY env vars before deploying to production."
        )
    return self
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "fix: allow default keys in development mode (warn instead of raise)"
```

---

### Task 3: Fix pgvector migration (move to alembic chain, fix column type)

**Files:**
- Create: `alembic/versions/002_vector_chunks.py`
- Delete: `migrations/versions/add_vector_chunks.py` (wrong directory, was never applied)

The existing migration at `migrations/versions/add_vector_chunks.py` is in the wrong directory (`alembic.ini` points to `alembic/`), has `down_revision = None` (breaks the chain), and uses `ARRAY(Float())` instead of pgvector's `vector` type. Replace it entirely.

- [ ] **Step 1: Create correct migration**

Create `alembic/versions/002_vector_chunks.py`:

```python
"""Add document_chunks table with pgvector HNSW index.

Revision ID: 002_vector_chunks
Revises: 001_initial
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_vector_chunks"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add vector column via raw SQL (pgvector type not in SQLAlchemy core)
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1536) NOT NULL DEFAULT array_fill(0, ARRAY[1536])::vector")

    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    op.create_foreign_key(
        "fk_document_chunks_document_id",
        "document_chunks", "documents",
        ["document_id"], ["id"],
        ondelete="CASCADE",
    )

    # HNSW index for cosine similarity ANN search
    op.execute("""
        CREATE INDEX ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Remove the DEFAULT constraint after table creation
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding DROP DEFAULT")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_constraint("fk_document_chunks_document_id", "document_chunks", type_="foreignkey")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
```

- [ ] **Step 2: Delete the old misplaced migration**

```bash
rm migrations/versions/add_vector_chunks.py
```

- [ ] **Step 3: Verify alembic sees the new migration**

```bash
cd cyberguard
alembic history
```

Expected output includes `002_vector_chunks -> (head)` with `down_revision = 001_initial`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/002_vector_chunks.py
git rm migrations/versions/add_vector_chunks.py
git commit -m "fix: move vector_chunks migration to alembic chain, use vector(1536) type"
```

---

### Task 4: Fix DocumentChunk model to use pgvector Vector type

**Files:**
- Modify: `app/models/knowledge.py`

- [ ] **Step 1: Update DocumentChunk.embedding column type**

In `app/models/knowledge.py`, replace the imports and the `DocumentChunk.embedding` column:

```python
# Add at top of file, after existing imports
from pgvector.sqlalchemy import Vector
```

Then in `DocumentChunk` class, replace:
```python
# Before
    # 1536-dim float array matching text-embedding-3-small
    embedding = Column(ARRAY(Float()), nullable=False)
```

```python
# After
    embedding = Column(Vector(1536), nullable=False)
```

Also remove the now-unused import `from sqlalchemy import Column, Float, Integer, ...` — remove `Float` from the import list since it's no longer used:

```python
# Before
from sqlalchemy import Column, Float, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import ARRAY

# After
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
from pgvector.sqlalchemy import Vector
```

- [ ] **Step 2: Verify import works**

```bash
cd cyberguard
python -c "from app.models.knowledge import DocumentChunk; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/models/knowledge.py
git commit -m "fix: use pgvector Vector(1536) type for DocumentChunk.embedding"
```

---

### Task 5: Normalize chat output_data so frontend can read it

**Files:**
- Modify: `app/workers/tasks.py`

The master agent stores `state["final_summary"]` but `_update_execution_with_result_sync` saves the raw state dict. `Chat.tsx` looks for `result.output_data.response` — always undefined.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (or create `tests/test_workers.py`):

```python
# tests/test_workers.py
def test_output_normalization():
    """output_data written to DB must have 'response' key."""
    from app.workers.tasks import _normalize_output
    state = {"final_summary": "hello world", "current_state": "END"}
    result = _normalize_output(state)
    assert result["response"] == "hello world"


def test_output_normalization_missing_summary():
    """Falls back to empty string if final_summary absent."""
    from app.workers.tasks import _normalize_output
    result = _normalize_output({})
    assert result["response"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_workers.py -v
```

Expected: ImportError — `_normalize_output` does not exist yet.

- [ ] **Step 3: Implement `_normalize_output` and wire it up**

In `app/workers/tasks.py`, add this function near the top (after imports):

```python
def _normalize_output(state: dict) -> dict:
    """Extract final_summary from agent state into a consistent {response: ...} dict."""
    return {"response": state.get("final_summary", "") if isinstance(state, dict) else ""}
```

Then in `run_master_agent_task`, find this block:

```python
        # Update status to completed with result
        future = _executor.submit(
            _update_execution_with_result_sync, execution_id, "completed", result, None
        )
```

Replace `result` with `_normalize_output(result)`:

```python
        # Update status to completed with result
        future = _executor.submit(
            _update_execution_with_result_sync, execution_id, "completed", _normalize_output(result), None
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_workers.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/workers/tasks.py tests/test_workers.py
git commit -m "fix: normalize output_data to {response:...} so Chat.tsx can read it"
```

---

### Task 6: Add /tasks/stats endpoint

**Files:**
- Modify: `app/routers/tasks.py`
- Modify: `webui/src/api/client.ts`

- [ ] **Step 1: Add stats endpoint to tasks router**

In `app/routers/tasks.py`, add after the existing imports:

```python
from datetime import datetime, timedelta
```

Then add this route at the end of the file:

```python
@router.get("/tasks/stats")
async def get_task_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """Aggregate execution stats: totals by status, daily counts for last 7 days."""
    from sqlalchemy import func, cast, Date

    # Count by status
    status_rows = await db.execute(
        select(AgentExecution.status, func.count(AgentExecution.id).label("cnt"))
        .group_by(AgentExecution.status)
    )
    by_status = {row.status: row.cnt for row in status_rows}

    # Daily counts for last 7 days
    cutoff = datetime.utcnow() - timedelta(days=7)
    daily_rows = await db.execute(
        select(
            cast(AgentExecution.created_at, Date).label("day"),
            func.count(AgentExecution.id).label("cnt"),
        )
        .where(AgentExecution.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    )
    by_day = [{"day": str(row.day), "count": row.cnt} for row in daily_rows]

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_day": by_day,
    }
```

- [ ] **Step 2: Add API method to client.ts**

In `webui/src/api/client.ts`, add inside the `api` object after `deleteTask`:

```typescript
  getTaskStats: () => request('/tasks/stats'),
```

- [ ] **Step 3: Verify endpoint responds**

Start the API locally or via Docker, then:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/tasks/stats
```

Expected: `{"total": 0, "by_status": {}, "by_day": []}` (or real data if tasks exist).

- [ ] **Step 4: Commit**

```bash
git add app/routers/tasks.py webui/src/api/client.ts
git commit -m "feat: add /tasks/stats aggregation endpoint"
```

---

### Task 7: Add GET/PATCH /config/settings for Security page

**Files:**
- Modify: `app/routers/config.py`
- Modify: `webui/src/api/client.ts`

Settings are stored in Redis under key `platform:settings` (no migration needed).

- [ ] **Step 1: Add settings endpoints to config router**

In `app/routers/config.py`, replace the imports block at the top:

```python
"""System configuration export/import router."""
import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_role
from app.core.rbac import Role

router = APIRouter()

_SETTINGS_KEY = "platform:settings"
_DEFAULT_SETTINGS = {
    "encryption_enabled": True,
    "audit_logging": True,
    "rbac_enabled": True,
    "api_key_rotation_days": 90,
    "max_login_attempts": 5,
    "session_timeout_minutes": 30,
    "require_mfa": False,
}
```

Then add these two routes **before** the existing `export_config` route:

```python
@router.get("/config/settings")
async def get_settings(_=Depends(require_role(Role.ADMIN))):
    """Return current platform security settings."""
    from app.core.redis_client import get_redis
    r = await get_redis()
    raw = await r.get(_SETTINGS_KEY)
    return json.loads(raw) if raw else dict(_DEFAULT_SETTINGS)


@router.patch("/config/settings")
async def update_settings(
    updates: dict,
    _=Depends(require_role(Role.ADMIN)),
):
    """Update one or more platform security settings."""
    from app.core.redis_client import get_redis
    r = await get_redis()
    raw = await r.get(_SETTINGS_KEY)
    current = json.loads(raw) if raw else dict(_DEFAULT_SETTINGS)
    allowed_keys = set(_DEFAULT_SETTINGS.keys())
    for key, value in updates.items():
        if key in allowed_keys:
            current[key] = value
    await r.set(_SETTINGS_KEY, json.dumps(current))
    return current
```

- [ ] **Step 2: Add API methods to client.ts**

In `webui/src/api/client.ts`, add inside the `api` object after `importConfig`:

```typescript
  getSecuritySettings: () => request('/config/settings'),
  updateSecuritySettings: (body: Record<string, unknown>) =>
    request('/config/settings', { method: 'PATCH', body: JSON.stringify(body) }),
```

- [ ] **Step 3: Verify endpoints work**

```bash
curl -X GET -H "Authorization: Bearer <admin_token>" http://localhost:8000/api/v1/config/settings
# Expected: {"encryption_enabled": true, "audit_logging": true, ...}

curl -X PATCH -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"require_mfa": true}' \
  http://localhost:8000/api/v1/config/settings
# Expected: full settings dict with require_mfa: true
```

- [ ] **Step 4: Commit**

```bash
git add app/routers/config.py webui/src/api/client.ts
git commit -m "feat: add GET/PATCH /config/settings stored in Redis"
```

---

### Task 8: Add streaming LLM output with Redis pub/sub

**Files:**
- Modify: `app/services/llm_router.py`

Add `execution_id` parameter to `LLMRouter.chat()`. When set, use `stream=True` and publish each delta + a final `done` event to Redis channel `task:{execution_id}`.

- [ ] **Step 1: Modify LLMRouter.chat() to support streaming**

In `app/services/llm_router.py`, find the `chat()` method signature and replace it:

```python
# Before
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
    ) -> str:
```

```python
# After
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
        execution_id: Optional[str] = None,
    ) -> str:
```

Then, inside `chat()`, after `client = await self.get_client_async(...)` and after the mock-mode block, add the streaming branch. Find the block that starts:

```python
        with tracer.start_as_current_span(
            f"llm.chat/{active_model}",
```

Replace the entire `with tracer...` block (the non-mock path) with:

```python
        with tracer.start_as_current_span(
            f"llm.chat/{active_model}",
            attributes={
                "llm.model": active_model,
                "llm.operation": "chat",
                "llm.num_messages": len(messages),
            },
        ) as span:
            if execution_id:
                # Streaming path: publish deltas to Redis for SSE
                from app.core.redis_client import cache as _cache
                import json as _json

                stream = await client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    temperature=settings.MASTER_AGENT_TEMPERATURE,
                    stream=True,
                )
                full_text = ""
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        full_text += delta
                        await _cache.publish(
                            f"task:{execution_id}",
                            {"type": "delta", "content": delta},
                        )
                await _cache.publish(
                    f"task:{execution_id}",
                    {"type": "done", "content": full_text},
                )
                span.set_attribute("llm.response_length", len(full_text))
                return full_text
            else:
                # Non-streaming path (original)
                response = await client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    temperature=settings.MASTER_AGENT_TEMPERATURE,
                )
                content = response.choices[0].message.content
                span.set_attribute("llm.response_length", len(content))
                span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)
                return content
```

- [ ] **Step 2: Verify import**

```bash
python -c "from app.services.llm_router import LLMRouter; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/llm_router.py
git commit -m "feat: add streaming path to LLMRouter.chat() with Redis pub/sub"
```

---

### Task 9: Pass execution_id through Master Agent state

**Files:**
- Modify: `app/agents/master.py`
- Modify: `app/agents/states.py`

The `execution_id` lives in `AgentExecution.execution_id` and is passed to the Celery task. It needs to flow through the LangGraph state to `_summarizer_node` so `llm_router.chat()` can publish to the right Redis channel.

- [ ] **Step 1: Add execution_id to MasterAgentState**

Open `app/agents/states.py`. Find `MasterAgentState` (it's a TypedDict). Add `execution_id` field:

```python
# Find the class and add this field (exact position depends on existing fields)
execution_id: Optional[str]   # UUID of AgentExecution record, for SSE streaming
```

- [ ] **Step 2: Pass execution_id in MasterAgent.run()**

In `app/agents/master.py`, find `MasterAgent.run()`:

```python
    async def run(self, user_input: str, user_id: int, **kwargs) -> Dict[str, Any]:
        """Run the master agent with user input."""
        initial_state = MasterAgentState(
            user_input=user_input,
            user_id=user_id,
            current_state=AgentState.START,
            group_chat_active=False,
            **kwargs,
        )
```

The `execution_id` is already in `**kwargs` because `run_master_agent_task` calls:
```python
master_agent.run(user_input=user_input, user_id=user_id)
```

But it does NOT pass execution_id. Fix `_run_async_master_agent` in `app/workers/tasks.py` to pass it:

```python
# In _run_async_master_agent, find:
    async def _run():
        master_agent = get_master_agent()
        return await master_agent.run(
            user_input=user_input,
            user_id=user_id,
            **kwargs,
        )
```

Add `execution_id` explicitly:

```python
    async def _run():
        master_agent = get_master_agent()
        return await master_agent.run(
            user_input=user_input,
            user_id=user_id,
            execution_id=execution_id,
            **kwargs,
        )
```

- [ ] **Step 3: Use execution_id in _summarizer_node**

In `app/agents/master.py`, find `_summarizer_node`. Locate the `llm_router.chat()` call:

```python
            try:
                state["final_summary"] = await self.llm_router.chat(
                    messages=[{"role": "user", "content": user_input}],
                    provider_id=state.get("provider_id"),
                    model=state.get("model"),
                )
```

Add `execution_id` parameter:

```python
            try:
                state["final_summary"] = await self.llm_router.chat(
                    messages=[{"role": "user", "content": user_input}],
                    provider_id=state.get("provider_id"),
                    model=state.get("model"),
                    execution_id=state.get("execution_id"),
                )
```

- [ ] **Step 4: Verify import**

```bash
python -c "from app.agents.master import MasterAgent; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/agents/states.py app/agents/master.py app/workers/tasks.py
git commit -m "feat: thread execution_id through LangGraph state to enable SSE streaming"
```

---

### Task 10: Add SSE stream endpoint to chat router

**Files:**
- Modify: `app/routers/chat.py`

`EventSource` in browsers cannot send custom headers, so auth uses `?token=` query param (same pattern as the existing GroupChat WebSocket endpoint). On connect, first check if the task already completed (race condition guard), then subscribe to Redis pub/sub.

- [ ] **Step 1: Add SSE endpoint**

In `app/routers/chat.py`, add these imports at the top:

```python
from typing import Optional, AsyncGenerator
from fastapi.responses import StreamingResponse
```

Then add this route at the end of the file:

```python
@router.get("/chat/stream/{task_id}")
async def stream_chat_sse(
    task_id: str,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE endpoint for real-time chat streaming.
    Auth via ?token= query param (EventSource cannot send headers).
    Subscribes to Redis channel task:{task_id} and forwards delta/done events.
    """
    from app.core.auth import decode_access_token
    from app.core.redis_client import get_redis
    from app.models.agent import AgentExecution
    from sqlalchemy import select
    import json as _json
    import asyncio

    if not token:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "token required"})

    try:
        payload = await decode_access_token(token)
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "invalid token"})

    async def event_stream() -> AsyncGenerator[str, None]:
        # Race condition guard: if task already completed, send stored response immediately
        result = await db.execute(
            select(AgentExecution).where(AgentExecution.execution_id == task_id)
        )
        execution = result.scalar_one_or_none()
        if execution and execution.status == "completed":
            response_text = ""
            if isinstance(execution.output_data, dict):
                response_text = execution.output_data.get("response", "")
            data = _json.dumps({"type": "done", "content": response_text})
            yield f"data: {data}\n\n"
            return
        if execution and execution.status == "failed":
            data = _json.dumps({"type": "error", "content": execution.error_message or "Task failed"})
            yield f"data: {data}\n\n"
            return

        # Subscribe to Redis pub/sub channel
        r = await get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(f"task:{task_id}")

        try:
            deadline = asyncio.get_event_loop().time() + 120
            while asyncio.get_event_loop().time() < deadline:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=1),
                        timeout=16,
                    )
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                if message is None:
                    yield ": keep-alive\n\n"
                    continue

                msg_data = _json.loads(message["data"])
                yield f"data: {_json.dumps(msg_data)}\n\n"

                if msg_data.get("type") in ("done", "error"):
                    break
        finally:
            await pubsub.unsubscribe(f"task:{task_id}")
            await pubsub.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

- [ ] **Step 2: Verify endpoint is registered**

```bash
python -c "from app.routers.chat import router; routes = [r.path for r in router.routes]; print(routes)"
```

Expected output includes `/chat/stream/{task_id}`.

- [ ] **Step 3: Commit**

```bash
git add app/routers/chat.py
git commit -m "feat: add SSE /chat/stream/{task_id} endpoint for real-time streaming"
```

---

### Task 11: Replace Chat.tsx polling with EventSource

**Files:**
- Modify: `webui/src/pages/Chat.tsx`

Remove the 2-second polling loop. Open an `EventSource` immediately after receiving `task_id`. Stream `delta` events into the last message in real-time.

- [ ] **Step 1: Replace the send() function**

In `webui/src/pages/Chat.tsx`, find the `send` function and replace it entirely:

```typescript
  const send = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input.trim(), created_at: new Date().toISOString() }
    const sentInput = input.trim()
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // Add empty assistant placeholder
    setMessages(prev => [...prev, { role: 'assistant', content: '', created_at: new Date().toISOString() }])

    try {
      const chatResp = await api.chat({ message: sentInput, ...getModelOverride() }) as { task_id: string }
      const taskId = chatResp.task_id
      const token = localStorage.getItem('token') || ''
      const evtSource = new EventSource(`/api/v1/chat/stream/${taskId}?token=${encodeURIComponent(token)}`)

      evtSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'delta') {
            setMessages(prev => {
              const msgs = [...prev]
              const last = msgs[msgs.length - 1]
              msgs[msgs.length - 1] = { ...last, content: last.content + data.content }
              return msgs
            })
          } else if (data.type === 'done') {
            if (data.content) {
              setMessages(prev => {
                const msgs = [...prev]
                msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: data.content }
                return msgs
              })
            }
            evtSource.close()
            setLoading(false)
          } else if (data.type === 'error') {
            setMessages(prev => {
              const msgs = [...prev]
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: `⚠ ERROR — ${data.content}` }
              return msgs
            })
            evtSource.close()
            setLoading(false)
          }
        } catch {
          // ignore parse errors
        }
      }

      evtSource.onerror = () => {
        evtSource.close()
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (!last.content) {
            msgs[msgs.length - 1] = { ...last, content: '⚠ CONNECTION LOST' }
          }
          return msgs
        })
        setLoading(false)
      }
    } catch (e: any) {
      setMessages(prev => {
        const msgs = [...prev]
        msgs[msgs.length - 1] = {
          ...msgs[msgs.length - 1],
          content: `⚠ SYSTEM ERROR — ${e?.message || 'TRANSMISSION FAILURE'}`,
        }
        return msgs
      })
      setLoading(false)
    }
  }
```

- [ ] **Step 2: Remove now-unused state**

Remove the `pollingStatus` state declaration and any references to it:

```typescript
// Remove this line:
const [pollingStatus, setPollingStatus] = useState('')
```

Also remove the loading indicator text that referenced `pollingStatus`:

```typescript
// Find and remove this in the loading JSX:
{pollingStatus || 'PROCESSING...'}
// Replace with simply:
{'PROCESSING...'}
```

- [ ] **Step 3: Build to verify no TypeScript errors**

```bash
cd cyberguard/webui
npm run build 2>&1 | tail -20
```

Expected: build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
cd ..
git add webui/src/pages/Chat.tsx
git commit -m "feat: replace polling with EventSource for real-time chat streaming"
```

---

### Task 12: Fix Schedule.tsx — cron → cron_expression field

**Files:**
- Modify: `webui/src/pages/Schedule.tsx`

Backend `ScheduledTask` model and `ScheduleTaskCreate` schema use `cron_expression`. Frontend `Task` interface uses `cron`. This causes tasks to be created with a null cron expression and never fire.

- [ ] **Step 1: Fix the Task interface and all references**

In `webui/src/pages/Schedule.tsx`:

Replace the `Task` interface:
```typescript
// Before
interface Task {
  id?: string
  name: string
  task_type: string
  cron?: string
  agent_id?: string
  payload?: any
  is_active?: boolean
  next_run?: string
}
```

```typescript
// After
interface Task {
  id?: string
  name: string
  task_type: string
  cron_expression?: string
  agent_id?: string
  task_config?: any
  is_active?: boolean
  next_run_at?: string
}
```

Replace the initial form state:
```typescript
// Before
const [form, setForm] = useState<Task>({ name: '', task_type: 'scheduled', cron: '' })
```

```typescript
// After
const [form, setForm] = useState<Task>({ name: '', task_type: 'scheduled', cron_expression: '' })
```

Find the reset in the "NEW TASK" button's onClick and in `submit`:
```typescript
// All occurrences of:
setForm({ name: '', task_type: 'scheduled', cron: '' })
// Replace with:
setForm({ name: '', task_type: 'scheduled', cron_expression: '' })
```

Find any `form.cron` reference in the JSX form field and change to `form.cron_expression`:
```typescript
// Before (the cron input field)
value={form.cron || ''}
onChange={e => setForm(f => ({ ...f, cron: e.target.value }))}
placeholder="*/5 * * * *"

// After
value={form.cron_expression || ''}
onChange={e => setForm(f => ({ ...f, cron_expression: e.target.value }))}
placeholder="*/5 * * * * (every 5 min)"
```

Find any display of `item.cron` in the task list and change to `item.cron_expression`:
```typescript
// Before (wherever the cron is displayed in the list)
{item.cron}
// After
{item.cron_expression}
```

Find `item.next_run` and change to `item.next_run_at`.

- [ ] **Step 2: Build to verify**

```bash
cd cyberguard/webui
npm run build 2>&1 | tail -10
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add webui/src/pages/Schedule.tsx
git commit -m "fix: use cron_expression field name to match backend ScheduledTask model"
```

---

### Task 13: Fix GroupChat.tsx WebSocket authentication

**Files:**
- Modify: `webui/src/pages/GroupChat.tsx`

`new WebSocket(url)` sends no auth. Backend `groupchat_websocket` accepts `?token=` query param as fallback.

- [ ] **Step 1: Add token to WebSocket URL**

In `webui/src/pages/GroupChat.tsx`, find the `connect` function:

```typescript
// Before
  const connect = (room: string) => {
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`${wsBase}/groupchat/${room}`)
```

```typescript
// After
  const connect = (room: string) => {
    if (wsRef.current) wsRef.current.close()
    const token = localStorage.getItem('token') || ''
    const ws = new WebSocket(`${wsBase}/groupchat/${room}?token=${encodeURIComponent(token)}`)
```

- [ ] **Step 2: Build to verify**

```bash
cd cyberguard/webui
npm run build 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add webui/src/pages/GroupChat.tsx
git commit -m "fix: pass JWT token as query param to GroupChat WebSocket"
```

---

### Task 14: Connect Security.tsx to backend settings

**Files:**
- Modify: `webui/src/pages/Security.tsx`

Load settings on mount from `GET /api/v1/config/settings`. Save each toggle change via `PATCH /api/v1/config/settings`.

- [ ] **Step 1: Replace Security.tsx content**

Replace the entire `Security.tsx` file content:

```typescript
import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Key, Lock, AlertTriangle, Loader2 } from 'lucide-react'

interface SecuritySettings {
  encryption_enabled: boolean
  audit_logging: boolean
  rbac_enabled: boolean
  api_key_rotation_days: number
  max_login_attempts: number
  session_timeout_minutes: number
  require_mfa: boolean
}

const DEFAULT_SETTINGS: SecuritySettings = {
  encryption_enabled: true,
  audit_logging: true,
  rbac_enabled: true,
  api_key_rotation_days: 90,
  max_login_attempts: 5,
  session_timeout_minutes: 30,
  require_mfa: false,
}

export default function Security() {
  const [settings, setSettings] = useState<SecuritySettings>(DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)

  useEffect(() => {
    api.getSecuritySettings()
      .then((data: any) => setSettings({ ...DEFAULT_SETTINGS, ...data }))
      .catch(() => {/* use defaults */})
      .finally(() => setLoading(false))
  }, [])

  const update = async (key: keyof SecuritySettings, value: any) => {
    const updated = { ...settings, [key]: value }
    setSettings(updated)
    setSaving(key)
    try {
      await (api as any).updateSecuritySettings({ [key]: value })
    } catch {
      setSettings(settings) // revert on error
    } finally {
      setSaving(null)
    }
  }

  const Toggle = ({ enabled, onToggle, color = 'var(--cyan)' }: { enabled: boolean; onToggle: () => void; color?: string }) => (
    <button onClick={onToggle}
      style={{
        position: 'relative', width: 44, height: 22,
        background: enabled ? color : 'var(--bg-elevated)',
        border: `1px solid ${enabled ? color : 'var(--border-bright)'}`,
        cursor: 'pointer', transition: 'all 0.2s',
      }}>
      <div style={{
        position: 'absolute', top: 2, left: 2,
        width: 16, height: 16,
        background: enabled ? color : 'var(--text-dim)',
        transition: 'all 0.2s',
        transform: enabled ? 'translateX(22px)' : 'translateX(0)',
      }} />
    </button>
  )

  const SettingRow = ({ icon, title, desc, settingKey, color = 'var(--cyan)' }: {
    icon: React.ReactNode; title: string; desc: string
    settingKey: keyof SecuritySettings; color?: string
  }) => (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', marginBottom: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ width: 38, height: 38, border: '1px solid var(--border-bright)', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', color }}>
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em', marginBottom: 4 }}>{title}</div>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{desc}</div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {saving === settingKey && <Loader2 size={12} style={{ color: 'var(--text-dim)', animation: 'spin 1s linear infinite' }} />}
        <Toggle enabled={settings[settingKey] as boolean} onToggle={() => update(settingKey, !settings[settingKey])} color={color} />
      </div>
    </div>
  )

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60 }}>
      <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
    </div>
  )

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>SECURITY CONTROLS</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SECURITY SETTINGS</h1>
        </div>
      </div>

      <SettingRow icon={<Lock size={16} />} title="ENCRYPTION AT REST" desc="AES-256 encryption for sensitive data and API keys" settingKey="encryption_enabled" />
      <SettingRow icon={<Key size={16} />} title="AUDIT LOGGING" desc="Log all API requests and agent executions" settingKey="audit_logging" color="var(--amber)" />
      <SettingRow icon={<AlertTriangle size={16} />} title="RBAC ENFORCEMENT" desc="Role-based access control for all endpoints" settingKey="rbac_enabled" color="var(--red)" />
      <SettingRow icon={<Lock size={16} />} title="REQUIRE MFA" desc="Multi-factor authentication for all admin users" settingKey="require_mfa" color="var(--purple)" />

      <div style={{ marginTop: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {[
          { label: 'API KEY ROTATION (DAYS)', key: 'api_key_rotation_days' as const },
          { label: 'MAX LOGIN ATTEMPTS', key: 'max_login_attempts' as const },
          { label: 'SESSION TIMEOUT (MIN)', key: 'session_timeout_minutes' as const },
        ].map(({ label, key }) => (
          <div key={key} style={{ padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
            <div style={{ fontSize: 9, letterSpacing: '0.15em', color: 'var(--text-muted)', marginBottom: 8 }}>{label}</div>
            <input
              type="number"
              value={settings[key] as number}
              onChange={e => update(key, parseInt(e.target.value))}
              style={{
                width: '100%', height: 36, padding: '0 10px',
                background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)',
              }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build to verify**

```bash
cd cyberguard/webui
npm run build 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add webui/src/pages/Security.tsx
git commit -m "fix: connect Security page toggles to GET/PATCH /config/settings backend"
```

---

### Task 15: Fix Providers.tsx — dynamic routing table

**Files:**
- Modify: `webui/src/pages/Providers.tsx`

The "MODEL ROUTING TABLE" section renders 3 hardcoded rows. Replace with a dynamic list built from `availableModels` (already loaded from the API at the top of the component).

- [ ] **Step 1: Replace the hardcoded routing table**

In `webui/src/pages/Providers.tsx`, find the "Model Routing Table" section. It contains a `tbody` with hardcoded `.map()` over a literal array. Replace that `tbody` block:

```typescript
{/* Remove this hardcoded block: */}
{[{ agent: 'MASTER AGENT', provider: 'GROK API (xAI)', models: 'grok-3, grok-3-mini' }, ...].map((row, i) => (
  ...
))}
```

```typescript
{/* Replace with dynamic data from loaded providers: */}
{items.length === 0 ? (
  <tr>
    <td colSpan={4} style={{ padding: '20px 16px', textAlign: 'center', fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>
      NO PROVIDERS CONFIGURED — ADD A PROVIDER ABOVE
    </td>
  </tr>
) : items.map((p) => (
  <tr key={p.id} style={{ borderBottom: '1px solid var(--border)' }}>
    <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-primary)', letterSpacing: '0.05em' }}>
      {p.name.toUpperCase()}
    </td>
    <td style={{ padding: '14px 16px', fontSize: 11, color: TYPE_COLORS[p.provider_type] || 'var(--green)', letterSpacing: '0.05em' }}>
      {TYPE_LABELS[p.provider_type] || p.provider_type}
    </td>
    <td style={{ padding: '14px 16px', fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
      {(p.models || []).join(', ') || '—'}
    </td>
    <td style={{ padding: '14px 16px' }}>
      <span style={{ fontSize: 9, letterSpacing: '0.1em', color: p.is_active ? 'var(--green)' : 'var(--text-dim)' }}>
        {p.is_active ? '● ACTIVE' : '○ INACTIVE'}
      </span>
    </td>
  </tr>
))}
```

Also update the table header to match (change "CURRENT PROVIDER" → "TYPE", "ACTION" → "STATUS"):

```typescript
{['PROVIDER NAME', 'TYPE', 'AVAILABLE MODELS', 'STATUS'].map((h, i) => (
  <th key={i} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
))}
```

- [ ] **Step 2: Build to verify**

```bash
cd cyberguard/webui
npm run build 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add webui/src/pages/Providers.tsx
git commit -m "fix: replace hardcoded Providers routing table with dynamic provider list"
```

---

### Task 16: Connect TokenUsage.tsx to /tasks/stats

**Files:**
- Modify: `webui/src/pages/TokenUsage.tsx`

Replace `MOCK_DATA` with real execution stats from `/tasks/stats`. Show counts by status and a daily activity bar chart.

- [ ] **Step 1: Replace TokenUsage.tsx**

Replace entire file content:

```typescript
import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Coins, Loader2 } from 'lucide-react'

interface Stats {
  total: number
  by_status: Record<string, number>
  by_day: { day: string; count: number }[]
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 100, flexShrink: 0, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <div style={{ flex: 1, height: 14, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', transition: 'all 0.3s' }} />
      </div>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 32, textAlign: 'right', letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }}>{value}</span>
    </div>
  )
}

export default function TokenUsage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getTaskStats()
      .then((data: any) => setStats(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const completed = stats?.by_status?.['completed'] ?? 0
  const failed = stats?.by_status?.['failed'] ?? 0
  const pending = (stats?.by_status?.['pending'] ?? 0) + (stats?.by_status?.['running'] ?? 0)
  const total = stats?.total ?? 0
  const maxDay = Math.max(1, ...(stats?.by_day?.map(d => d.count) ?? [0]))

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60 }}>
      <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
    </div>
  )

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>COST ANALYSIS</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>TASK USAGE</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Coins size={16} style={{ color: 'var(--accent)' }} />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'TOTAL EXECUTIONS', value: String(total), color: 'var(--cyan)' },
          { label: 'COMPLETED', value: String(completed), color: 'var(--green)' },
          { label: 'FAILED', value: String(failed), color: 'var(--red)' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color, letterSpacing: '0.05em', marginBottom: 6 }}>{value}</div>
            <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.15em' }}>{label}</div>
          </div>
        ))}
      </div>

      {stats?.by_day && stats.by_day.length > 0 && (
        <div style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16 }}>DAILY EXECUTIONS (LAST 7 DAYS)</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {stats.by_day.map(d => (
              <Bar key={d.day} label={d.day.slice(5)} value={d.count} max={maxDay} />
            ))}
          </div>
        </div>
      )}

      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-bright)' }}>
              {['STATUS', 'COUNT', 'PERCENT'].map((h, i) => (
                <th key={i} style={{ padding: '12px 16px', textAlign: i === 0 ? 'left' : 'right', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(stats?.by_status ?? {}).map(([status, count]) => (
              <tr key={status} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '14px 16px', fontSize: 11, fontFamily: 'var(--font-mono)', color: status === 'completed' ? 'var(--green)' : status === 'failed' ? 'var(--red)' : 'var(--text-muted)', letterSpacing: '0.05em' }}>{status.toUpperCase()}</td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{count}</td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {total > 0 ? ((count / total) * 100).toFixed(1) + '%' : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build to verify**

```bash
cd cyberguard/webui
npm run build 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add webui/src/pages/TokenUsage.tsx
git commit -m "fix: replace TokenUsage mock data with real /tasks/stats API"
```

---

### Task 17: Update architecture documents

**Files:**
- Modify: `01_System_Design_Document_EN.md`
- Modify: `02_SUB_AGENTS.md`
- Modify: `03_MASTER_AGENT.md`
- Modify: `04_API_AND_BACKEND.md`
- Modify: `05_WEBUI_DESIGN.md`
- Modify: `06_DEPLOYMENT_AND_SECURITY.md`
- Modify: `07_IMPLEMENTATION_ROADMAP.md`

- [ ] **Step 1: Update 01_System_Design_Document_EN.md**

Add/replace the chat pipeline section to describe SSE flow:

```markdown
## Chat Pipeline

**Request flow (updated):**
1. User submits message → `POST /api/v1/chat` → returns `{task_id, status: "pending"}`
2. Frontend immediately opens `EventSource /api/v1/chat/stream/{task_id}?token=...`
3. Celery Worker picks up task → runs Master Agent → LLM streams via OpenAI stream=True
4. Each LLM delta → `redis.publish("task:{task_id}", {type:"delta", content:"..."})`
5. FastAPI SSE handler subscribes → forwards delta events → browser updates in real time
6. LLM done → publish `{type:"done"}` → SSE closes

**Knowledge Base:** Uses pgvector HNSW index on `document_chunks.embedding vector(1536)` for cosine similarity search. Docker image: `pgvector/pgvector:pg16`.
```

- [ ] **Step 2: Update 02_SUB_AGENTS.md**

Add note about streaming output:

```markdown
## Streaming Output

Sub-agent results are collected by the Master Agent's `_sub_agent_executor_node`.
When the Master Agent's `_summarizer_node` calls `LLMRouter.chat()`, it passes
`execution_id` which enables streaming: each LLM token is published to
`Redis channel task:{execution_id}` as `{type:"delta", content:"..."}`.
```

- [ ] **Step 3: Update 03_MASTER_AGENT.md**

Add `execution_id` to the state description:

```markdown
## State Fields (additions)

- `execution_id: str` — UUID from AgentExecution table, threaded through state from Celery task to `_summarizer_node` for SSE streaming.

## _summarizer_node

Calls `LLMRouter.chat(..., execution_id=state["execution_id"])`.
When execution_id is set, LLMRouter uses `stream=True` and publishes deltas to Redis.
```

- [ ] **Step 4: Update 04_API_AND_BACKEND.md**

Add new endpoints:

```markdown
## New Endpoints (v1.1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/chat/stream/{task_id}` | SSE stream for real-time chat output. Auth via `?token=` |
| GET | `/api/v1/tasks/stats` | Execution counts by status and daily breakdown |
| GET | `/api/v1/config/settings` | Platform security settings (admin only) |
| PATCH | `/api/v1/config/settings` | Update platform security settings (admin only) |
```

- [ ] **Step 5: Update 05_WEBUI_DESIGN.md**

Update Chat page description:

```markdown
## Chat Page

Uses `EventSource` (SSE) for real-time streaming. Flow:
1. `POST /api/v1/chat` → get task_id
2. Open `new EventSource(/api/v1/chat/stream/{task_id}?token=...)` 
3. `onmessage` appends delta text to last assistant message bubble
4. `done` event closes connection

Security page now persists settings via `PATCH /api/v1/config/settings`.
Providers routing table is dynamic (loaded from API, not hardcoded).
TokenUsage page shows real execution stats from `/api/v1/tasks/stats`.
GroupChat WebSocket authenticates via `?token=` query param.
```

- [ ] **Step 6: Update 06_DEPLOYMENT_AND_SECURITY.md**

Update Docker Compose section:

```markdown
## Docker Compose Services

- **postgres**: `pgvector/pgvector:pg16` (includes pgvector extension for vector similarity search)
- **redis**: `redis:7-alpine` (used for rate limiting, pub/sub SSE streaming, platform settings)
- **api**: FastAPI + Uvicorn
- **celery_worker**: Celery worker (concurrency=4)
- **flower**: Celery monitoring UI
- **webui**: React app via Nginx

## Development Mode

`ENVIRONMENT=development` in `.env` bypasses the strict encryption key validator.
Default keys are logged as warnings. Always set `ENCRYPTION_KEY` and `SECRET_KEY` before production.
```

- [ ] **Step 7: Update 07_IMPLEMENTATION_ROADMAP.md**

Replace content with updated roadmap:

```markdown
# Implementation Roadmap

## Completed (v1.1)
- [x] Docker Compose deployment (FastAPI + PostgreSQL/pgvector + Redis + Celery)
- [x] JWT authentication + RBAC
- [x] AI Provider management (CRUD + connection test)
- [x] Agent configuration management
- [x] Skills & Tools management
- [x] Knowledge Base with pgvector HNSW semantic search
- [x] MCP server & tool management
- [x] Scheduled tasks (cron-based)
- [x] Audit logging
- [x] Backup / Restore
- [x] Env var management
- [x] Human approval workflow
- [x] SSE real-time streaming chat
- [x] GroupChat WebSocket (authenticated)
- [x] Security settings page (persistent)
- [x] Task usage stats dashboard

## Next Steps (v1.2)
- [ ] Token usage tracking (store usage data from OpenAI response)
- [ ] MFA enforcement
- [ ] API key rotation automation
- [ ] Sub-agent SDK for custom agent deployment
```

- [ ] **Step 8: Commit all doc changes**

```bash
git add 01_System_Design_Document_EN.md 02_SUB_AGENTS.md 03_MASTER_AGENT.md \
        04_API_AND_BACKEND.md 05_WEBUI_DESIGN.md 06_DEPLOYMENT_AND_SECURITY.md \
        07_IMPLEMENTATION_ROADMAP.md
git commit -m "docs: update architecture docs to reflect SSE streaming and pgvector changes"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Covered By |
|---|---|
| 1. docker-compose pgvector | Task 1 |
| 1. config dev-mode key | Task 2 |
| 2.1 config key fix | Task 2 |
| 2.2 chat output mismatch | Task 5 |
| 2.3 schedule cron field | Task 12 |
| 2.4 groupchat WS auth | Task 13 |
| 2.5 security page backend | Tasks 7 + 14 |
| 2.6 providers routing table | Task 15 |
| 2.7 token usage | Tasks 6 + 16 |
| 3.1 Redis channel convention | Task 8 |
| 3.2 SSE stream endpoint | Task 10 |
| 3.3 master agent streaming | Tasks 8 + 9 |
| 3.4 Chat.tsx EventSource | Task 11 |
| 4.1 docker pgvector | Task 1 |
| 4.2 migration | Tasks 3 + 4 |
| 4.3 knowledge service | Tasks 3 + 4 (service already implemented) |
| 5. architecture docs | Task 17 |

All spec sections are covered. ✓

### Type Consistency

- `execution_id` added to `MasterAgentState` (Task 9 Step 1) and passed in `_run_async_master_agent` (Task 9 Step 2) and used in `_summarizer_node` (Task 9 Step 3) and accepted by `LLMRouter.chat()` (Task 8). ✓
- `cron_expression` renamed consistently in `Task` interface, form state, onChange handlers, and display (Task 12). ✓
- `getTaskStats` in `api/client.ts` (Task 6 Step 2) matches `api.getTaskStats()` call in `TokenUsage.tsx` (Task 16). ✓
- `api.getSecuritySettings()` and `api.updateSecuritySettings()` added to client.ts (Task 7 Step 2) and used in Security.tsx (Task 14). ✓
