---
name: project_status
description: CyberGuard platform implementation status — last updated 2026-05-30 (PR #2 merged; all 54 non-DB tests green on Python 3.9)
type: project
---

# CyberGuard Project Status — 2026-05-30

## ▶ Resume point (next session)

- **Branch:** `main` — PR #2 merged (commit e74c9b9). `feat/internal-agents` fully landed.
- **Just finished:** Merged PR #2 (QwenPaw pool alignment ①②③ + test-infra). Fixed Python 3.9 compat in 6 router files (`X | None → Optional[X]`); all 54 non-DB tests now pass locally.
- **Next up:** Decide M6 scope. Remaining known issues:
  - `test_smoke_api.py` excluded from pytest via root `conftest.py` (`collect_ignore`) — run standalone with `python -m unittest tests.test_smoke_api` when server is up
  - WebUI: Custom agents don't show API key in UI (API-only for now)
  - `has_manifest` is per-message (not top-level on PollResponse) — idle nodes w/no pending tasks won't see it until next task is dispatched; nodes can call `/gateway/manifest` proactively with their API key

## Milestones (1-5 complete)

- **M1** — Backend Foundation: FastAPI + Postgres + Celery ✅
- **M2** — LLM Integration: Multi-provider router + intent parsing ✅
- **M3** — Sub-Agent System: external (OpenClaw/Hermes/Custom) + internal (in-app) ✅
- **M4** — WebUI: React + Vite + TypeScript ✅
- **M5** — Agent Collaboration: Multi-agent routing + group chat panel ✅
- **QwenPaw pool alignment** — ① executable Tool pool ✅ · ② unified assignment + tags ✅ · ③ external agents use pools ✅ (PR #2)

## Alembic head

`012_pool_assignment_tags` (latest)

Sequence: `… → 010_agent_kind_and_internal → 011_tool_executable → 012_pool_assignment_tags`

---

## Session 2026-05-29 — Unified pool assignment + tags (QwenPaw alignment, subproject ②)

Shipped subproject ② (spec `docs/superpowers/specs/2026-05-29-pool-assignment-tags-design.md`,
plan `docs/superpowers/plans/2026-05-29-pool-assignment-tags.md`):

- **Migration 012** — `AgentConfig` gains `associated_tools` + `associated_mcp_tools`
  JSON columns (joining `associated_skills`); `Skill`/`Tool`/`MCPTool` gain `tags`.
  Data migration moves `metadata_json.tool_ids`/`mcp_tool_ids` into the new columns
  and removes those keys; reversible downgrade.
- **Read points** — `InternalAgentRunner` resolves ids column-first with a
  `metadata_json` fallback; `AgentExecutor` threads the columns into `config_dict`.
- **API** — agent + pool CRUD round-trip the new fields automatically (create via
  `hasattr` filter, update via `setattr`, pool create via `model_dump`); `?tag=`
  filter on `/skills`, `/tools`, `/mcp/tools/all` (post-filter `total`).
- **WebUI** — internal-agent form gets Skills/Tools/MCP multi-select assignment
  pickers (`PoolPicker`); Skills/Tools pages get a tags editor; all three pool
  pages show tags (+ version on Skill/Tool) and a tag-filter box. MCP tools have
  no tags editor (server-discovered, not user-created) — tags settable via API.

Executed via subagent-driven development (6 tasks, two-stage review each, plus a
final whole-implementation review + a stale-`total` follow-up fix). The ①
temporary `metadata_json.tool_ids` wiring is superseded by `associated_tools`
(fallback retained).

**Deferred to ③:** external agents using the pools (payload delivery + gateway
callbacks); `get_mcp_tools_for_agent` refactor to read `associated_mcp_tools`.

---

## Session 2026-05-29 — Executable Tool pool (QwenPaw alignment, subproject ①)

Shipped subproject ① of aligning the skill/tool/mcp pools with QwenPaw (spec
`docs/superpowers/specs/2026-05-29-tool-pool-executable-design.md`, plan
`docs/superpowers/plans/2026-05-29-tool-pool-executable.md`). The Tool pool went
from doc-only to **executable**:

- **Tool model** (migration 011) gains `command_template`, `input_schema_json`,
  `timeout_seconds`, `required_permission`; `md_content` now optional.
- **`tool_executor.py`** — injection-safe argv builder (shlex-split template,
  placeholders → single argv tokens, no shell; type/enum validation) +
  `execute_tool` (RBAC + high-permission approval + dispatch).
- **`tool-runner`** — new isolated container (docker-compose), FastAPI `/run`
  runs argv via `create_subprocess_exec` (no shell), `start_new_session` +
  process-group kill on timeout, `X-Runner-Token` auth (fails fast if unset),
  no host port.
- **API** — `POST /api/v1/tools/{id}/execute` (TASK_EXECUTE + per-tool RBAC).
- **Internal agent** — executable Tools are callable via temporary
  `metadata_json.tool_ids` (becomes `associated_tools` in subproject ②);
  high-permission tools create an approval request.
- **WebUI** — new **Tools** page (`webui/src/pages/Tools.tsx`) with executable
  form fields + EXECUTABLE badge + TEST button.

Executed via subagent-driven development (8 tasks, two-stage review each, plus a
final whole-implementation review). Tests: `tests/test_tool_executor.py` (13) +
internal-agent pool-tool test pass.

**Deferred to ②/③:** unified `associated_tools` assignment + tags/version on the
pools (②); external agents using the pools via payload delivery + gateway
callbacks (③).

---

## Session 2026-05-29 — Scheduled-tasks model export + WebUI port + conversations-table hotfix

Small follow-up changes on `feat/internal-agents`:

- **`app/models/__init__.py`** — export `ScheduledTask` and `Conversation` from the `app.models` package (import + `__all__`). Both models existed and were used (the `/api/v1/schedule` CRUD router and the conversations router import them directly), but neither was re-exported through the package, so `from app.models import ScheduledTask`/`Conversation` failed. Tables are migration-driven, so this did not affect table creation — only the package import surface.
- **`docker-compose.yml`** — WebUI host port `3000 → 3001` (host port only; container still serves on `80`) to avoid a local port collision.

> ⚠️ The schedule feature remains **CRUD-only**: there is no Alembic migration for the `scheduled_tasks` table and no Celery-beat executor, so stored cron expressions are persisted but not yet executed. Tracked under "Not yet implemented".

### Hotfix — missing `conversations` table / orphaned Alembic revision

Login landing page returned `{"detail":"Internal server error"}`. Root cause was **not** auth — the page creates a conversation on load and the insert failed with `UndefinedTableError: relation "conversations" does not exist`.

Diagnosis: the DB `alembic_version` was stamped to **`e6977c6f81d8`** — an orphaned revision id that exists in **no** migration file. Earlier in development that revision (the "agent kind" migration) added the `agent_configs` columns but did **not** create `conversations`; it was later renamed to `010_agent_kind_and_internal` and gained the `CREATE TABLE IF NOT EXISTS conversations` guard. Because the DB stayed pinned to the orphaned hash, Alembic believed it was already at head and `010` never re-ran, so `conversations` was never created (while `agent_configs` already had the new columns).

Fix applied directly to the dev DB in one transaction (NOT a `stamp 009 + upgrade` — that would re-`ADD COLUMN` the already-present `agent_configs` columns and fail):

```sql
BEGIN;
-- create conversations in its final 010 shape (11 base cols + agent_id + parent_conversation_id + ix_conv_agent + FKs)
CREATE TABLE IF NOT EXISTS conversations ( ... );
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS agent_id INTEGER REFERENCES agent_configs(id) ON DELETE CASCADE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS parent_conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_conv_agent ON conversations (agent_id, parent_conversation_id);
UPDATE alembic_version SET version_num = '010_agent_kind_and_internal';
COMMIT;
```

Verified: `alembic current` → `010`; real admin login → `POST /api/v1/conversations` 201, `GET` 200. Fresh installs are unaffected (010 runs cleanly from 001). Only DBs pinned to the orphaned revision need this one-time realignment.

---

## Session 2026-05-28 — Internal (Configurable) Sub-Agents

A new **kind** of sub-agent is now fully implemented. See `docs/superpowers/specs/2026-05-28-internal-agents-design.md` and `docs/superpowers/plans/2026-05-28-internal-agents-plan.md`.

### What shipped

- **Migration 010** — adds `kind` + internal config cols to `agent_configs`; `agent_id` + `parent_conversation_id` to `conversations`; `ix_conv_agent` composite index.
- **Models** — `AgentConfig` (kind, llm_provider_id, llm_model, tool_loop_max_steps, memory_window, knowledge_base_id); `Conversation` (agent_id, parent_conversation_id FK).
- **LLM Router** — `chat()` gains `tools` kwarg; returns `str` (no tools) or `ChatCompletionMessage` with `.tool_calls` (tools provided); mock mode handles both.
- **InternalAgentRunner** — async tool-call loop via LLM Router; per-agent memory slices in `conversations`; skill bodies → system prompt; MCP tools + synthetic `kb_search` as callable tools; `knowledge_service` via `_KSAdapter` (own session).
- **MCP Executor** — extracted `_execute_stdio_tool` / `_execute_http_tool` into `app/services/mcp_executor.py`; router re-imports shared state.
- **AgentExecutor** — `execute()` + `execute_parallel()` gain `context: dict | None`; dispatches `kind=internal` → `InternalAgentRunner`, external → existing paths.
- **Master + GroupChat** — `conversation_id` threaded through `MasterAgentState`, `executor.execute()` calls, and `GroupChatSession.parent_conversation_id`.
- **Pydantic schemas + CRUD** — `AgentConfigBase/Update/Read` gain all new fields; `_validate_agent_payload()` enforces kind-specific rules (external requires backend_type; internal requires llm_provider_id, forbids endpoint_url/backend_type).
- **WebUI** — kind badge (blue=internal), filter buttons (ALL/EXTERNAL/INTERNAL), kind-chooser modal on NEW AGENT, internal-agent form with LLM Provider ID + LLM Model fields, edit restores internal field values.
- **Seed** — `SEED_EXAMPLE_INTERNAL_AGENTS=true` on startup creates `triage_analyst` + `policy_writer` idempotently.
- **Smoke tests** — `test_internal_agent_crud` + `test_internal_agent_validation` in `tests/test_smoke_api.py`.

### 20 commits on `feat/internal-agents`

```
49ad547 feat(agents): migration 010 — agent kind + internal cols + conv.agent_id
317fda1 fix(migration): create conversations table idempotently in 010
eec0c44 feat(models): add kind/internal columns to AgentConfig and agent_id to Conversation
8a2847c fix(models): align Conversation index with migration composite + trailing newline
51c9743 refactor(mcp): extract execute_stdio/http_tool into mcp_executor service
3585124 feat(llm-router): accept tools kwarg, return ChatCompletionMessage when set
6930761 fix(llm-router): consistent tools-guard + safer SimpleNamespace return
e428b24 feat(agents): InternalAgentRunner skeleton + memory load/save
628b278 fix(agents): drop unused imports flagged by review
de359c4 feat(agents): InternalAgentRunner — skill prompt assembly + tool catalog
297ff51 fix(agents): guard non-dict input_schema_json
3211114 feat(agents): InternalAgentRunner — dispatch + execute tool-call loop
b27c91d fix(agents): handle str router response + hoist get_llm_router import
6f011ca feat(executor): route kind=internal to InternalAgentRunner; thread context
d360bcf fix(executor): add trailing newline at EOF
0d5aba7 feat(agents): thread conversation_id through master + group chat
d0e4488 feat(agents): kind-aware Pydantic schemas + CRUD validation
dc2066a feat(webui): kind badge + filter + chooser modal + internal form on Agents page
7491dfe feat(agents): seed example internal agents (env-gated)
7d52741 feat(smoke): test internal agent CRUD + kind validation
```

---

## Previous sessions

### Governance/GRC (2026-05-13/14)

- `app/routers/governance.py` — Frameworks → Requirements → ComplianceAssessments → Evidence full CRUD.
- ISO 27001:2022 (93 controls) + NIST CSF 2.0 (~106 subcategories) seeded on startup.
- `typical_evidence` checklist (5–8 items per control, ~1000 total) seeded per requirement.
- AI endpoints: `/ai-suggest-evidence`, `/ai-assess`, `/ai-report` (nginx proxy_read_timeout raised to 300s).
- Evidence upload: `kind ∈ {text, url, file}` schema exists; UI wires text + url (file upload pending).

### Webhooks (2026-05-13)

- Bidirectional: incoming token-hash + outgoing HMAC-SHA256.
- Celery task `deliver_webhook_task` with exp-backoff ×3 on transient errors.
- SSRF protection blocks RFC1918 / metadata IPs.
- `emit("approval.required", ...)` fired from `ApprovalService.create_request`.

### Chat refactor (2026-05-12)

- WebSocket room chat deleted; group chat is REST + Redis only.
- Mode switch: NORMAL / FAST / EXPERT; explicit `agent_id` selector bypasses intent parser.
- `MasterAgentState` gains `agent_id`, `mode`, `conversation_id`.
- `llm_router._get_agents_info()` injects live agent list into system prompts.

### Knowledge Base (2026-05-12)

- `pgvector/pgvector:pg16` Postgres image; `pypdf` + `python-docx` for binary ingest.
- XOR CHECK on `embedding` (1536-dim) vs `embedding_large` (3072-dim halfvec).
- Per-KB dim locked and immutable via `knowledge_bases.embedding_dim`.

### Prompt Templates (2026-05-14)

- 9 seeded cyber-ops templates (system / intent_parser / summarizer / general categories).
- Chat CUSTOM SYSTEM PROMPT has TEMPLATE dropdown.

---

## Not yet implemented

- S3 / Alibaba OSS backup (API stub exists, no implementation).
- Email notifications for every event surface (helpers exist).
- Streaming sub-agent output (currently batch — in scope for future internal-agent streaming).
- Guardrail sanitization pass (`GuardrailResult.sanitized` field reserved but not implemented).
- Full integration test suite (only `tests/test_smoke_api.py`).
- OCR for scanned-image PDFs (text-only works via pypdf).
- Governance evidence file upload (`kind=file` schema exists, UI not wired).
- Internal agent streaming output.
- Scheduled-tasks execution: `/api/v1/schedule` CRUD + `ScheduledTask` model exist, but no Alembic migration for `scheduled_tasks` and no Celery-beat executor — cron expressions are stored, never run.
- **Test isolation for DB-backed async tests** ✅ (fixed 2026-05-30): root `conftest.py` excludes `test_smoke_api.py` from pytest collection via `collect_ignore`. The smoke test uses `asyncio.run()` in `setUpClass` which creates a separate event loop, poisoning the module-level SQLAlchemy async engine's connection pool. It remains runnable standalone via `python -m unittest tests.test_smoke_api` when a server is running. All 71 non-smoke tests pass together cleanly.

## Operational notes

- After pulling, rebuild api + webui: `docker compose build api webui`.
- Run `docker compose exec api alembic upgrade head` to advance to `010_agent_kind_and_internal`.
- To seed example internal agents: `SEED_EXAMPLE_INTERNAL_AGENTS=true` in environment.
- Internal agent memory slices: `conversations` rows with `agent_id` + `parent_conversation_id`. Each internal agent gets its own slice per parent conversation.
- `_KSAdapter` in `internal_agent.py` opens its own `AsyncSessionLocal()` for KB queries — no caller-supplied session needed.
- `llm_router.chat()` dual-return contract: `str` (no tools) / `ChatCompletionMessage` with `.tool_calls` (tools provided). Internal agent loop checks `isinstance(msg, str)` first.