# AGENTS.md — CyberGuard coding-agent rules

Rules for AI coding assistants working in this repository.

## Forbidden

- Do not run `git push --force`, `git reset --hard`, or `git clean -fd` unless the user explicitly asks.
- Do not commit secrets, `.env`, or decrypted API keys.
- Do not write exploit payloads, malware, or attack scripts against live systems.
- Do not set `AUTO_APPROVE=true` or insecure HTTP/API-key flags in production configs.
- Do not re-introduce a blocking `wait_for_decision` poll in the master approval node — use `interrupt()` + checkpointer.

## How to run tests

```bash
# Infra (from cyberguard/)
docker compose up -d postgres redis

# Suite (uses the project venv)
.venv/bin/python -m pytest tests/ -q
```

- The test DB is shared and non-transactional. Prefer matching on your own
  `run_id` / `request_id` rather than asserting global row counts.
- `test_smoke_api.py` needs a running API and is not part of the default suite.

## Migrations

```bash
alembic -c alembic.ini upgrade head
```

Current head after the agent-core audit includes `032_agent_run_events`.
LangGraph also creates its own checkpoint tables via `AsyncPostgresSaver.setup()`.

## Architecture facts that bite

1. **Two engines**: LangGraph master orchestrates; the internal-agent tool loop
   runs outside the graph. Loop progress is surfaced via `agent_run_events` and
   `state["loop_events"]`.
2. **Approval must not block workers**: `_approval_node` uses `interrupt()`.
   Resume is `MasterAgent.resume` / `resume_master_agent_task`.
3. **Gate once**: pool tools pass `governance=None` into `execute_tool` because
   the `before_tool` hook already gated them. Gating twice double-audits and
   creates two approval requests.
4. **Retrieved content is annotated, never blocked** by
   `check_untrusted_content` — blocking would let a planted trigger DoS the agent.
5. **`_validation_decision` reads `approval_required`** only after the
   non-blocking interrupt path landed; do not route more traffic into a
   blocking wait.
6. **One approval authorises one dispatch.** A decision is valid only for the
   `approval_round` it was granted in (`_approval_is_current`); the executor
   node spends it and bumps the round. Never gate on a bare
   `approval_status == "approved"` — it persists for the whole thread and would
   wave through every later gate.
7. **`interrupt()` discards the writes the node made before suspending.** Any
   "do this once" guard in the approval node must be keyed off the DB
   (`approval_request_id()` + `get_by_request_id`), never off graph state.
8. **`pre_approved` must reach the executor.** It is read by
   `AgentExecutor.execute` and `InternalAgentRunner`; if a new dispatch path
   drops it, approving stops actually running the approved action.

## Git discipline under concurrent sessions

- One logical change per commit; do not mix migration + unrelated UI.
- Update `docs/superpowers/plans/project_status.md` and the audit backlog when
  closing inventory items.
- Prefer `GRAPH_CHECKPOINT_BACKEND=memory` under pytest (auto when
  `PYTEST_CURRENT_TEST` is set).
