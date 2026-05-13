---
name: project_status
description: CyberGuard platform implementation status — last updated 2026-05-13
type: project
---

# CyberGuard Project Status — 2026-05-13

## Milestones (1-5 complete)

- **M1** — Backend Foundation: FastAPI + Postgres + Celery ✅
- **M2** — LLM Integration: Multi-provider router + intent parsing ✅
- **M3** — Sub-Agent System: OpenClaw gateway + hermes/custom HTTP push ✅
- **M4** — WebUI: React + Vite + TypeScript ✅
- **M5** — Agent Collaboration: Multi-agent routing + group chat panel ✅

## Alembic head

`006_webhooks` (latest)

Sequence: `001_initial → 002_openclaw_gateway → 003_pgvector_knowledge → 004_multi_dim_embeddings → 005_drop_room_chat → 006_webhooks`

## Session 2026-05-11 → 05-13 — Major changes

### Chat — sub-agent routing (2026-05-11)

- `app/agents/states.py` — `MasterAgentState` gains `agent_id`, `mode` fields.
- `app/agents/master.py`:
  - `_parse_intent_node`: dispatch precedence is now (1) explicit `agent_id` from UI → (2) `mode=fast` → (3) `mode=expert` (fan out to all active sub-agents) → (4) normal LLM intent parsing.
  - `_sub_agent_executor_node`: `_routable()` predicate accepts OpenClaw agents without `endpoint_url` (they go through the Gateway poll/report flow).
- `app/services/llm_router.py`:
  - `_get_agents_info()` returns `(name, url, backend, description)` tuples; intent-parser prompt and direct-chat system prompt both inject this list so the LLM never claims it "can't see sub-agents".
  - `build_chat_system_prompt(base, mode, expert_no_agents)` — mode-aware system prompt builder used by `_summarizer_node`'s direct LLM fallback.
- `app/routers/chat.py` — `/chat` and `/chat/attachments` propagate `agent_id` + `mode` to Celery kwargs.
- WebUI:
  - `webui/src/pages/Chat.tsx` — toolbar gets a 3-segment MODE switch (NORMAL / FAST / EXPERT) and an AGENT dropdown ("MASTER (AUTO ROUTE)" + every active sub-agent). Both persisted in localStorage. IME composition (`isComposing` / `keyCode === 229`) early-return in `handleKey` so Chinese-input Enter no longer sends mid-composition.
  - `webui/src/api/client.ts` — `chat()` and `uploadChatAttachments()` carry `agent_id` + `mode`.

### Sub-agent onboarding (2026-05-11)

- `webui/src/pages/Agents.tsx` `OpenClawGuide` — single self-installing prompt block (replaces the prior three-step skill+heartbeat+hint UI). User pastes once into OpenClaw; the prompt instructs it to (1) create `skills/cyberguard_sync.md` with API-key-baked content, (2) append the heartbeat trigger to `HEARTBEAT.md`, (3) ping `/heartbeat` + `/poll` to verify. Edit-mode warning banner has a **GENERATE NEW KEY** button — calls `POST /agents/{id}/api-key`, drops the new plaintext key into the prompt instantly.

### Knowledge Base (2026-05-12)

- `docker-compose.yml` — Postgres image is now `pgvector/pgvector:pg16` (was `postgres:16-alpine`).
- `pyproject.toml` — adds `pypdf>=4.0.0`, `python-docx>=1.1.0`.
- `app/models/knowledge.py`:
  - `KnowledgeBase.embedding_dim` int NOT NULL DEFAULT 1536 with CHECK `IN (1536, 3072)`. Immutable.
  - `DocumentChunk.embedding vector(1536) NULL` + `embedding_large halfvec(3072) NULL` with XOR CHECK constraint (exactly one populated per row).
- Migrations:
  - **003** — `CREATE EXTENSION vector`, swap legacy `double precision[]` → `vector(1536)`, partial HNSW.
  - **004** — add `knowledge_bases.embedding_dim`, add `embedding_large halfvec(3072)` column, XOR CHECK, partial HNSW for both columns (vector_cosine_ops / halfvec_cosine_ops).
- `app/services/knowledge_service.py`:
  - `extract_text(raw, mime, filename)` for binary ingest: pypdf for PDF, python-docx for `.docx` (paragraphs + table cells), UTF-8 decode otherwise.
  - `ingest_document` / `query` route reads/writes to the dim-appropriate column, validates dim match, casts to `::vector(1536)` or `::halfvec(3072)` at query time.
- `app/routers/knowledge.py` — `upload_document` uses `extract_text` instead of UTF-8 decode.
- WebUI:
  - `webui/src/pages/Knowledge.tsx` — KB create form auto-derives `embedding_dim` from selected model name (`text-embedding-3-large` → 3072 else 1536), shows `DIM: 3072` badge live, KB card list shows model + dim.
  - Upload `accept` extended to `.pdf,.docx,application/pdf,...wordprocessingml...`.

### Group chat refactor (2026-05-12)

- Deleted the WebSocket-based human room chat entirely.
- `app/routers/groupchat.py` — slim file containing only multi-agent REST session endpoints.
- `app/main.py` — `groupchat.router` re-mounted under `prefix="/api/v1"` (was `/ws` — that's why multi-agent silently 404'd before).
- Deleted `app/models/groupchat.py` and its entry from `app/models/__init__.py`.
- Migration **005** drops the `group_chat_messages` table.
- `webui/src/pages/GroupChat.tsx` — `HumanChat` function and tab switcher removed; page renders only `MultiAgentChat`.
- Design docs `01_System_Design_Document_EN.md` / `04_API_AND_BACKEND.md` / `05_WEBUI_DESIGN.md` / `README.md` — all WebSocket / room-chat references replaced or removed.

### Webhooks (2026-05-13)

- New ORM `app/models/webhook.py` — bidirectional single-table model (`direction` ∈ `incoming` | `outgoing`).
- New schemas `app/schemas/webhook.py` — `SUPPORTED_EVENTS = ('approval.required',)` is the single source of truth; service rejects unknown events.
- New service `app/services/webhook_service.py`:
  - `emit(event, payload)` — fan out to all active outgoing webhooks subscribed to the event, queue a Celery task per match (non-blocking).
  - `deliver_sync(webhook_id, event, payload)` — synchronous HTTP POST with HMAC-SHA256 signature (if secret set), SSRF allow-list (blocks RFC1918 / metadata IPs), updates trigger/success/failure counts + last_error on the webhook row.
- New router `app/routers/webhooks.py` — full CRUD + `/regenerate-token` + `/test` (sync test-fire) + public `POST /api/v1/webhooks/incoming/{token}` (no auth, token SHA-256 looked up, dispatches as Master Agent task).
- `app/workers/tasks.py` — `deliver_webhook_task` Celery task with exp-backoff ×3 on transient errors (connection / timeout). Permanent failures recorded on the row, not retried.
- `app/services/approval_service.py` — `ApprovalService.create_request` now fires `emit("approval.required", ...)` via `asyncio.create_task`.
- Migration **006** creates the `webhooks` table with unique name, direction CHECK, direction-fields XOR CHECK, indexes on id / name / `incoming_token_hash`.
- WebUI:
  - New page `webui/src/pages/Webhooks.tsx` — cards with direction color stripe (cyan=incoming / accent=outgoing), event badges, HMAC indicator, fire/success/fail counts, TEST + REGEN actions.
  - Sidebar adds "Webhooks" under FEATURES group; i18n added in both `en.json` / `zh.json`.
  - `webui/src/api/client.ts` — `getWebhooks`, `createWebhook`, `updateWebhook`, `deleteWebhook`, `regenWebhookToken`, `testWebhook`.

## Not yet implemented

- S3 / Alibaba OSS backup (API stub exists, no implementation).
- Email notifications for every event surface (helpers exist).
- Streaming sub-agent output (currently batch).
- Guardrail sanitization pass.
- Full integration test suite (only `tests/test_smoke_api.py`).
- OCR for scanned-image PDFs (text-only works).
- Additional webhook events: `task.completed` / `task.failed` / `agent.execute` / `schedule.fired` — designed but not yet emitted.

## Operational notes

- After pulling these changes from git, rebuild api + webui Docker images (`docker compose build api webui`). `pyproject.toml` has new deps (`pypdf`, `python-docx`) and `docker-compose.yml` Postgres image changed.
- Run `docker exec cyberguard-api-1 alembic upgrade head` to advance to `006_webhooks`.
- Existing `test` sub-agent + its OpenClaw API key remain valid; regenerating only happens when the user clicks REGEN KEY.
