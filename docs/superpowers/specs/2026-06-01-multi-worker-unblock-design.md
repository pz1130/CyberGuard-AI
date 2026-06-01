# Multi-Worker API Unblock — Design

**Date:** 2026-06-01
**Status:** Approved (brainstorming)
**Area:** `app/services/{master_config,security_settings,group_chat,mcp_executor}.py`, `app/workers/tasks.py`, `tool-runner/`, `Dockerfile`, `docker-compose.yml`

## Problem

The API runs a **single uvicorn worker**. Bumping `--workers` is unsafe because
three pieces of cross-request state live in one process's memory (per the
2026-05-30 audit, `multi-worker-blockers`):

1. 🔴 **MCP STDIO `_live_processes`** (`app/services/mcp_executor.py`) — live
   subprocess handles for STDIO MCP servers, keyed in a module-level dict. A
   subprocess handle cannot move to Redis. A stop/status/tool-call landing on a
   different worker than the one that started the server fails. (Aggravated
   today: STDIO servers are started in the **API** process via `routers/mcp.py`,
   but tool calls during an agent run happen in the **Celery** worker via
   `internal_agent.py` — two processes, two empty-or-divergent `_live_processes`.)
2. 🟠 **Config/security caches go stale** — `master_config.py` (`_config_cache`)
   and `security_settings.py` (`_cache`) have `invalidate_cache()` that only
   clears the **local** process; other workers serve stale config indefinitely.
3. 🟡 **Group-chat in-process state** — `group_chat.py` `_active_sessions` /
   `_completion_tasks`; `/complete` runs as an in-process `asyncio.create_task`.
   Cross-worker polling/idempotency breaks.

Agent orchestration itself already runs **off the API** (Celery
`run_master_agent_task` → `get_master_agent().run()`), so this work does **not**
re-architect agent execution. It removes the three in-API state blockers so the
API can run multiple uvicorn workers.

## Goal

API runs N uvicorn workers. All cross-request state is externalized to Redis or
to the single **tool-runner** process, which becomes the central MCP host.
Celery and tool-runner already run as separate processes. The worker count is
flipped only after all three blockers are resolved.

## Non-goals

- No JiuwenSwarm-style persistent-WebSocket agent-server. Agent execution is
  already decoupled via Celery; a second decoupling layer would be redundant.
- No change to agent orchestration logic, the LLM router, or guardrails.
- tool-runner stays **single-instance** (it is the dedicated stateful host).

## Design decisions (locked in brainstorming)

- **Cache invalidation:** Redis **version-number** (not pub/sub, not TTL).
- **Group-chat completion:** **Celery task + Redis-authoritative state** (not
  in-process asyncio with sticky routing).
- **MCP scope:** **only STDIO** relocates to tool-runner. (Revised during Phase 3
  planning: the tool-runner is deliberately minimal — fastapi+uvicorn only, no
  `httpx`/SSRF/`ENCRYPTION_KEY`/DB — so routing HTTP MCP through it would add deps
  and move SSRF/egress for zero multi-worker benefit. HTTP MCP is already stateless
  and worker-safe, so it stays in-process in `mcp_executor`.)

## Phased design

Each phase is independently shippable and **safe under single-worker**.
Multi-worker is flipped only in Phase 4.

### Phase 1 — Config/security cache → Redis version-number

- Each cache namespace gets a Redis integer version key: `cache:ver:master_config`,
  `cache:ver:security_settings`. Any mutation does `INCR cache:ver:<ns>`.
- Local cache holds `(version, value)`. On read: `GET cache:ver:<ns>` (cheap);
  if it differs from the locally-stored version, rebuild the local cache and
  store the new version. If Redis is unreachable, fall back to rebuild-every-read
  (degraded but correct).
- `invalidate_cache()` becomes `INCR cache:ver:<ns>` (global) instead of clearing
  a local dict.
- **Files:** new `app/core/versioned_cache.py` (shared GET-version / compare /
  rebuild helper); refactor `app/services/master_config.py` and
  `app/services/security_settings.py` to use it.
- **Tests:** a version bump performed by one cache instance is observed by a
  second instance sharing the same (fake) Redis → triggers a rebuild; Redis-down
  path rebuilds every read without error.

### Phase 2 — Group-chat state → Redis + Celery

- Authoritative session state moves from the in-process `_active_sessions` dict
  to Redis (`groupchat:session:<id>`, JSON or hash). All reads/writes go through
  Redis.
- The in-process completion run (`_completion_tasks`, `asyncio.create_task`) is
  replaced by a Celery task `run_group_chat_completion_task` (mirrors
  `run_master_agent_task`): any worker dispatches it; the orchestration runs in
  Celery; status/polling reads session state from Redis.
- Idempotency / single-runner: a Redis `SET NX` lock `groupchat:lock:<id>` with
  TTL guards dispatch so a duplicate `/complete` does not double-run.
- **Files:** `app/services/group_chat.py` (state → Redis), `app/workers/tasks.py`
  (new task), the group-chat router (dispatch via Celery + lock).
- **Tests:** session state round-trips through (fake) Redis; a second `/complete`
  while the lock is held is rejected/no-op; the completion path dispatches a
  Celery task (mocked) instead of an in-process task.

### Phase 3 — MCP central hosting in tool-runner

- tool-runner (existing FastAPI on :9000, `RUNNER_TOKEN` auth) gains an MCP host
  module that **owns the single authoritative `_live_processes`** for STDIO
  servers and passes through HTTP MCP. New token-authenticated internal endpoints:
  - `POST /mcp/servers/{name}/start`
  - `POST /mcp/servers/{name}/stop`
  - `GET /mcp/servers/{name}/status`
  - `GET /mcp/servers/{name}/tools`
  - `POST /mcp/servers/{name}/tools/{tool}/call`
- The hosting logic (`_live_processes`, `_start_stdio_server`,
  `_stop_stdio_server`, `execute_stdio_tool`, `execute_http_tool`, plus the
  command/args/env validation helpers) **moves from `app/services/mcp_executor.py`
  into the tool-runner service** (`tool-runner/mcp_host.py`).
- `app/services/mcp_executor.py` becomes a **thin client**: the same public
  function signatures (`execute_mcp_tool`, start/stop/status, etc.) but each makes
  an authenticated HTTP call to `TOOL_RUNNER_URL`. **Call sites in
  `app/routers/mcp.py` and `app/services/internal_agent.py` do not change** — they
  call the same functions, which simply no longer spawn subprocesses.
- Only STDIO MCP routes through tool-runner; HTTP MCP stays in-process in
  `mcp_executor` (stateless, already multi-worker safe). Decryption of per-server
  env happens client-side (tool-runner has no `ENCRYPTION_KEY`); command/arg
  validation happens in tool-runner (it is the spawning host).
- tool-runner restart resilience: STDIO servers are (re)started on demand; a call
  hitting a not-running server triggers an auto-start in tool-runner. The
  single-instance assumption is documented.
- **Files:** new `tool-runner/mcp_host.py` wired into the tool-runner app; rewrite
  `app/services/mcp_executor.py` as a client; verify (no change to)
  `app/routers/mcp.py` and `app/services/internal_agent.py`; `docker-compose.yml`
  already has tool-runner.
- **Tests:** the mcp_executor client hits a mocked tool-runner (request shape +
  error mapping); STDIO start/call/stop lifecycle inside tool-runner (integration,
  using a tiny echo MCP server); HTTP MCP passthrough.

### Phase 4 — Flip the switch + validation

- `Dockerfile` / `docker-compose.yml`: API runs
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-4}`.
  `API_WORKERS` is an env knob, so multi-worker is configurable and reversible.
- Validation checklist (manual, post-flip):
  1. Start a STDIO MCP server, then call its tool from a request that lands on a
     different API worker.
  2. Update a security setting; confirm every worker observes it on the next read.
  3. Start a group-chat `/complete`; poll status across workers and confirm a
     duplicate `/complete` is rejected by the lock.

## Cross-cutting

- **Error handling:** tool-runner unreachable → mcp_executor client surfaces a
  clear 503-style error (same UX as a dead STDIO server today). Redis unreachable
  → caches degrade to rebuild-every-read (correct); group-chat dispatch fails
  loudly rather than silently double-running.
- **Testing:** unit tests per phase run against fakes (fakeredis or a thin Redis
  interface, mocked HTTP for tool-runner); one integration smoke per phase. No
  reliance on a real Redis in unit tests.
- **Ordering rationale:** caches → group chat → MCP, easiest to hardest. If any
  phase slips, the system stays on single-worker with no regression, because the
  flip happens only in Phase 4.

## Risks

- **MCP relocation is the largest change** (multi-day, medium-high risk). Mitigated
  by keeping `mcp_executor` public signatures stable so call sites are untouched,
  and by phasing it last.
- **tool-runner becomes a single point of failure for all MCP.** Acceptable: it is
  already required for tool execution; document the single-instance assumption and
  the auto-restart-on-demand behavior.
- **Added Redis GET per config read (Phase 1).** Negligible vs. correctness; config
  reads are not on the hottest path and the version GET is O(1).
