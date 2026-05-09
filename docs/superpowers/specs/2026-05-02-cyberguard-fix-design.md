# CyberGuard Fix & Enhancement Design
**Date:** 2026-05-02  
**Scope:** Option B — Bug Fixes + SSE Streaming + Knowledge pgvector  
**Deployment Target:** Docker Compose

---

## 1. Architecture Overview

### What Stays the Same
- FastAPI + PostgreSQL + Redis + Celery + LangGraph stack
- Docker Compose deployment
- RBAC permission system
- Master Agent LangGraph state machine
- All existing API endpoint contracts

### Key Changes

#### Chat Response Pipeline (most critical)
**Before (broken):**
```
Frontend POST /chat → Celery dispatches → Frontend polls /tasks/{id} every 2s × 30 → timeout
```

**After:**
```
Frontend POST /chat → 202 + task_id
Frontend opens EventSource /api/v1/chat/stream/{task_id}
Celery Worker executes → publishes to Redis channel "task:{task_id}"
FastAPI SSE handler reads Redis → pushes delta events to frontend
LLM done → publish {type:"done"} → SSE closes
```

#### docker-compose.yml
- Replace `postgres:16` image with `pgvector/pgvector:pg16`

#### config.py startup fix
- Development environment skips encryption key strict validation, auto-generates random key and logs it

---

## 2. Bug Fixes

### 2.1 Config — Default Key Blocks Startup
**File:** `app/config.py`  
**Problem:** `validate_security_keys` raises `ValueError` when default keys are used, preventing first-time dev startup.  
**Fix:** In `ENVIRONMENT == "development"`, skip the validator and auto-generate a random key with a warning log. Production keeps strict validation.

### 2.2 Chat — Task Output Field Mismatch
**Files:** `app/workers/tasks.py`, `app/agents/master.py`  
**Problem:** `_summarizer_node` stores result as `{"final_summary": "..."}` in `output_data`, but `Chat.tsx` looks for `response`, `content`, or `text` keys — always gets `undefined`.  
**Fix:** In `_update_execution_with_result_sync`, normalize the output to `{"response": state["final_summary"]}` before writing to DB.

### 2.3 Schedule — Field Name Mismatch
**Files:** `webui/src/pages/Schedule.tsx`, `app/models/schedule.py`  
**Problem:** Frontend submits `cron` field; backend model uses `cron_expression`. Scheduled tasks are created but never fire.  
**Fix:** Update `Schedule.tsx` to use `cron_expression`. Add a cron syntax hint in the form (e.g. `*/5 * * * *`).

### 2.4 GroupChat WebSocket — No Authentication
**File:** `webui/src/pages/GroupChat.tsx`  
**Problem:** `new WebSocket(url)` connects without a token. Backend expects `Authorization` cookie or `?token=` query param. Connection is immediately rejected.  
**Fix:** Append `?token=${localStorage.getItem('token')}` to the WebSocket URL.

### 2.5 Security Page — Settings Not Persisted
**File:** `webui/src/pages/Security.tsx`  
**Problem:** All toggles are local React state only; nothing is saved to the backend.  
**Fix:** On mount, load settings from `GET /api/v1/config`. On toggle change, call `PUT /api/v1/config` with the updated key-value. The `config` router already supports import/export — extend it with a `PATCH /api/v1/config/settings` endpoint for incremental key updates.

### 2.6 Providers Page — Routing Table is Hardcoded Mock
**File:** `webui/src/pages/Providers.tsx`  
**Problem:** The "MODEL ROUTING TABLE" shows hardcoded rows (GROK API, QWEN TUNING, OLLAMA) regardless of what providers are actually configured.  
**Fix:** Replace hardcoded rows with a dynamic render of the `availableModels` list (already loaded from the providers API), grouped by agent type.

### 2.7 TokenUsage Page — Not Connected to Backend
**File:** `webui/src/pages/TokenUsage.tsx`  
**Problem:** Page shows no real data.  
**Fix:** Add `GET /api/v1/tasks/stats` endpoint that aggregates from `AgentExecution` table (count by status, by agent_type, by date). Frontend calls this on mount and renders the stats.

---

## 3. SSE Streaming

### 3.1 Redis Channel Convention
```
channel name: "task:{execution_id}"
message schema:
  {"type": "delta", "content": "<incremental text>"}
  {"type": "done",  "content": "<final full text>"}
  {"type": "error", "content": "<error message>"}
```

### 3.2 New Backend Endpoint
**File:** `app/routers/chat.py` (new route added)
```
GET /api/v1/chat/stream/{task_id}
Response: text/event-stream
Auth: Bearer token required
```
- Subscribes to Redis `task:{task_id}` pubsub channel
- Forwards each message as an SSE `data:` event
- Closes connection on `done` or `error` type
- 120-second hard timeout, sends `keep-alive` comments every 15s

### 3.3 Master Agent — Streaming Publisher
**File:** `app/agents/master.py`, `app/services/llm_router.py`

In `LLMRouter.chat()`, add a `stream=True` path:
- Call `client.chat.completions.create(..., stream=True)`
- For each chunk, `redis.publish("task:{execution_id}", {"type":"delta","content":chunk})`
- After all chunks, publish `{"type":"done","content":full_text}`

`_summarizer_node` passes `execution_id` through state so the publisher knows which channel to write to.

### 3.4 Frontend — Chat.tsx Rewrite (polling → EventSource)
**File:** `webui/src/pages/Chat.tsx`

Remove:
- `poll()` function
- `while (attempts < maxAttempts)` loop
- `pollingStatus` state

Add:
- `EventSource` opened immediately after receiving `task_id` from POST /chat
- `onmessage` handler appends `delta` content to assistant message in real-time
- `done`/`error` closes EventSource
- Cursor blinking animation while stream is open
- Reference QwenPaw streaming frontend implementation for EventSource pattern

---

## 4. Knowledge Base + pgvector

### 4.1 docker-compose.yml
```yaml
postgres:
  image: pgvector/pgvector:pg16
  # all other config unchanged
```

### 4.2 Alembic Migration
New migration file: `alembic/versions/add_pgvector_support.py`
```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE vector_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536);
CREATE INDEX ON vector_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 4.3 Knowledge Service Implementation
**File:** `app/services/knowledge_service.py`

**Ingest path:**
1. Receive document text
2. Split into chunks: 512 tokens, 50-token overlap
3. Call `LLMRouter.embed(chunks, provider_id=...)` → get embedding vectors
4. Batch-insert into `vector_chunks` table with `embedding` column

**Query path:**
1. Embed query string via `LLMRouter.embed([query])`
2. Run pgvector similarity search: `ORDER BY embedding <=> query_vec LIMIT top_k`
3. Apply `similarity_threshold` filter
4. Return matched chunks with scores

Reference QwenPaw knowledge/memory implementation for chunking strategy and similarity search patterns.

---

## 5. Architecture Document Updates

The following files in the project root must be updated to reflect all changes above:

| File | What to Update |
|------|---------------|
| `01_System_Design_Document_EN.md` | Chat pipeline diagram (polling → SSE), pgvector dependency |
| `02_SUB_AGENTS.md` | Streaming output from sub-agents via Redis pub/sub |
| `03_MASTER_AGENT.md` | SSE publishing in summarizer node |
| `04_API_AND_BACKEND.md` | New endpoints: `/chat/stream/{task_id}`, `/tasks/stats`, `PATCH /config/settings` |
| `05_WEBUI_DESIGN.md` | Chat page streaming UX, Security page backend integration |
| `06_DEPLOYMENT_AND_SECURITY.md` | pgvector image, dev-mode key auto-generation |
| `07_IMPLEMENTATION_ROADMAP.md` | Replace with updated phase plan reflecting completed and remaining work |

---

## 6. File Change Summary

| File | Change Type |
|------|------------|
| `docker-compose.yml` | postgres image → pgvector |
| `app/config.py` | dev-mode key validation skip |
| `app/routers/chat.py` | add `/chat/stream/{task_id}` SSE endpoint |
| `app/routers/tasks.py` | add `/tasks/stats` aggregation endpoint |
| `app/routers/config.py` | add `PATCH /config/settings` endpoint |
| `app/agents/master.py` | pass `execution_id` through state |
| `app/services/llm_router.py` | add streaming `chat()` path, publish to Redis |
| `app/workers/tasks.py` | normalize output to `{"response": ...}` |
| `app/services/knowledge_service.py` | implement ingest + vector query |
| `alembic/versions/add_pgvector_support.py` | new migration |
| `webui/src/pages/Chat.tsx` | replace polling with EventSource |
| `webui/src/pages/Schedule.tsx` | `cron` → `cron_expression` |
| `webui/src/pages/GroupChat.tsx` | add `?token=` to WS URL |
| `webui/src/pages/Security.tsx` | connect to `/config/settings` |
| `webui/src/pages/Providers.tsx` | dynamic routing table |
| `webui/src/pages/TokenUsage.tsx` | connect to `/tasks/stats` |
| `01_System_Design_Document_EN.md` | architecture update |
| `02_SUB_AGENTS.md` | streaming update |
| `03_MASTER_AGENT.md` | SSE publishing update |
| `04_API_AND_BACKEND.md` | new endpoints |
| `05_WEBUI_DESIGN.md` | UX changes |
| `06_DEPLOYMENT_AND_SECURITY.md` | pgvector + dev key |
| `07_IMPLEMENTATION_ROADMAP.md` | updated roadmap |
