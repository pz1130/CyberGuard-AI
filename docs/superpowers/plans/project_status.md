---
name: project_status
description: CyberGuard platform implementation status — last updated 2026-05-28 (internal agents shipped)
type: project
---

# CyberGuard Project Status — 2026-05-28

## Milestones (1-5 complete)

- **M1** — Backend Foundation: FastAPI + Postgres + Celery ✅
- **M2** — LLM Integration: Multi-provider router + intent parsing ✅
- **M3** — Sub-Agent System: external (OpenClaw/Hermes/Custom) + internal (in-app) ✅
- **M4** — WebUI: React + Vite + TypeScript ✅
- **M5** — Agent Collaboration: Multi-agent routing + group chat panel ✅

## Alembic head

`010_agent_kind_and_internal` (latest)

Sequence: `001_initial → 002_openclaw_gateway → 003_pgvector_knowledge → 004_multi_dim_embeddings → 005_drop_room_chat → 006_webhooks → 007_prompt_templates → 008_governance → 009_req_typical_evidence → 010_agent_kind_and_internal`

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

## Operational notes

- After pulling, rebuild api + webui: `docker compose build api webui`.
- Run `docker compose exec api alembic upgrade head` to advance to `010_agent_kind_and_internal`.
- To seed example internal agents: `SEED_EXAMPLE_INTERNAL_AGENTS=true` in environment.
- Internal agent memory slices: `conversations` rows with `agent_id` + `parent_conversation_id`. Each internal agent gets its own slice per parent conversation.
- `_KSAdapter` in `internal_agent.py` opens its own `AsyncSessionLocal()` for KB queries — no caller-supplied session needed.
- `llm_router.chat()` dual-return contract: `str` (no tools) / `ChatCompletionMessage` with `.tool_calls` (tools provided). Internal agent loop checks `isinstance(msg, str)` first.