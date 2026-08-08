---
name: agent-core-audit-backlog
description: 31-item audit of the agent core (loop / graph / prompt engineering), benchmarked against the pi agent harness. Phases 0-4 delivered 2026-08-07 (498 tests); residual low-priority items noted below.
type: project
---

# Agent Core Audit — Backlog and Delivery Record

**Date:** 2026-08-07
**Trigger:** comparison of `cyberguard`'s agent implementation against
[earendil-works/pi](https://github.com/earendil-works/pi), an agent harness whose
runtime (loop, session, compaction, skills) is more mature than ours even though
its governance surface is deliberately minimal.

## Framing

pi and cyberguard have opposite strengths and neither should be copied wholesale:

| | pi | cyberguard |
|---|---|---|
| Form | local single-user CLI | multi-user platform, 4 workers + Celery + PG/Redis |
| Permissions | **deliberately none** (containerise instead) | RBAC + approval + gatekeeper + kill switch + audit chain |
| Extension | arbitrary TypeScript | data-driven (MCP / Tool pool / Skill markdown) |
| Strength | **the agent runtime itself** | **the governance surface** |

Everything below is about the runtime, which is our thinner layer.

## Assessment of the three engineering axes

- **Loop engineering — present and deliberate.** `internal_agent._run_loop` has
  step caps, a tool-call budget, fingerprint-based loop detection, a reflector,
  auto-continue, LLM retry and context compaction. Gaps were termination
  semantics, budget dimensions and recoverability.
- **Graph engineering — a graph, but almost no engineering.** (pre-phase-3)
  `master.py` built a LangGraph `StateGraph` with **no back edges**, **no
  checkpointer**, and an unused `ToolNode` import. **Phase 3 closed this:**
  Postgres/`MemorySaver` checkpointer, `interrupt()` approval, validation
  back-edge replan, real scoring node, loop events in state.
- **Prompt engineering — infrastructure without method.** (pre-phase-4)
  Good three-layer override chain; missing registry and output contracts.
  **Phase 4 landed** a prompt registry and structured `generate_summary`.

---

## Inventory (31 items)

Status: ✅ delivered · ⬜ outstanding

### A. Crashes and correctness

| # | Item | Status |
|---|---|---|
| 1 | `key` unbound in the exception branch of `master._sub_agent_executor_node` | ✅ P0 |
| 2 | Episodic memory recorded every run as `success=True`, then recalled only successes — self-poisoning | ✅ P2 |
| 3 | Tool calls from a length-truncated response were executed with possibly-incomplete arguments | ✅ P0 |
| 4 | `max_steps=8` vs `tool_call_budget=100` — the budget branch was unreachable | ✅ P4 |

### B. Security and governance

| # | Item | Status |
|---|---|---|
| 5 | MCP / kb_search / web_search bypassed kill switch, gatekeeper and audit entirely | ✅ P1 (unified in P2) |
| 6 | No screening of retrieved content — indirect prompt injection surface | ✅ P1 (+ mid-string P4) |
| 7 | `needs_approval` / `denied` / `halted` were plain text the model could route around | ✅ P0 |
| 8 | Decrypted env vars sent in the request body over possibly-plaintext HTTP | ✅ P1 |
| 9 | `metadata_json.api_key` plaintext fallback used silently in production | ✅ P1 |
| 10 | `confidence` always `None`, so `escalate_to_human_below` never fires — dead configuration | ✅ P4 |
| 11 | `AUTO_APPROVE` defaulted to `True` | ✅ P1 |

### C. Agent loop core

| # | Item | Status |
|---|---|---|
| 12 | No termination contract on tool results | ✅ P0 (`ToolOutcome.terminate`) |
| 13 | Governance inlined in the dispatcher instead of a hook chain | ✅ P2 |
| 14 | No per-turn adaptation (cheap model for recon, escalate on a hit) | ⬜ residual |
| 15 | No `sequential` execution mode per tool — scans and firewall changes run in parallel | ✅ P4 |
| 16 | Concurrency of the shared counters rests on "no await before mutation", not a mechanism | ✅ P4 |
| 17 | Streaming path re-generated the final answer with a second tool-less call | ✅ P2 |

### D. Graph orchestration

| # | Item | Status |
|---|---|---|
| 18 | Graph has no back edges — validation failure cannot re-plan or re-execute | ✅ **P3** |
| 19 | No checkpointer: the graph cannot suspend, resume or time-travel | ✅ **P3** |
| 20 | `_approval_node` blocks a worker for up to an hour, polling a new DB session every 2s | ✅ **P3** |
| 21 | `_validation_node` is a placeholder: English keyword matching, hardcoded `risk_score`, literal `action_items` | ✅ **P3** |
| 22 | Two disconnected engines — `ToolNode` unused; the graph cannot see inside the loop | ✅ **P3** (completed post-review: the runner now returns `run_id`) |

### E. Session and state

| # | Item | Status |
|---|---|---|
| 23 | `messages_json` rewritten whole on every append — concurrent workers overwrite each other | ✅ P3 (`SELECT FOR UPDATE`) |
| 24 | No crash recovery point; no record of how far a run got | ✅ P2 + P3 recovery sweep |

### F. Context and prompts

| # | Item | Status |
|---|---|---|
| 25 | Token estimate under-counted Chinese 2-4x, so compaction fired after the window had already overflowed | ✅ P0 |
| 26 | Compaction threshold unrelated to the real model context window | ⬜ residual |
| 27 | Every bound skill's full body inlined into the system prompt, every turn | ✅ P2 |
| 28 | Prompts scattered across 7 modules; Chinese and English mixed within one request | ✅ P4 (registry; language rule in summarizer) |
| 29 | No output contract — downstream parses free text | ✅ P4 (`generate_summary` JSON) |

### G. Resources and consistency

| # | Item | Status |
|---|---|---|
| 30 | Retries fired back-to-back with no backoff (the `continue` was a no-op) | ✅ P0 |
| 31 | Dead code and drift: unreachable `_error_node`, hardcoded `EPISODE_EMBED_DIM`, mixed `sub_results` key types, stale README | ✅ P3/P4 (partial: `_error_node` now reachable; embed dim documented) |

### H. Evaluation (separate workstream)

No full agent-behaviour evaluation suite yet (injection red-team corpus beyond
governance, prompt regression baseline, loop convergence). Framework pieces
exist (faux providers in unit tests, `regressions/` naming still open).

---

## Delivered

### Phase 0 — stop the bleeding (2026-08-07)

| # | Change | Where |
|---|---|---|
| 1 | Bind `key` on the exception branch | `app/agents/master.py` |
| 3 | Refuse every tool call from a `finish_reason == "length"` response; propagate `finish_reason` out of the router | `internal_agent.py`, `llm_router.chat` |
| 7 | `ToolOutcome(text, status, terminate, trusted)`; refusals end the run and outrank the budget/loop guards | `internal_agent.py` |
| 25 | `estimate_text_tokens` counts CJK at ~1 token/char; `CONTEXT_COMPACT_CHARS=24000` → `CONTEXT_COMPACT_TOKENS=6000` | `core/context_compressor.py`, `internal_agent.py` |
| 30 | Exponential backoff between sub-agent retries | `agent_executor.py` |

### Phase 1 — close the holes (2026-08-07)

| # | Change | Where |
|---|---|---|
| 5 | `_govern()` runs kill switch + gatekeeper + audit for MCP, KB and search | `internal_agent.py` |
| 6 | All tool output fenced in `<untrusted_tool_output>`; new `check_untrusted_content()`; system prompt explains the tag | `core/guardrails.py`, `internal_agent.py` |
| 8 | `require_secure_endpoint()` mandates TLS; certificate verification unconditional | `agent_executor.py` |
| 9 | Plaintext `metadata_json.api_key` refused unless explicitly opted in | `agent_executor.py` |
| 11 | `AUTO_APPROVE=False` by default; three insecure flags are startup errors in production | `config.py` |

**Why retrieved content needs its own screen.** `check_prompt_sync` was tried
first and false-positives heavily: its markup rules (HTML, markdown links, code
fences) are what fetched pages and KB documents are *made of*, and its structural
rules (entropy, repetition) fire on Chinese prose and scan output. An alert that
fires constantly is not an alert. `check_untrusted_content` keeps only the
semantic rules — instruction override, jailbreak prefix, `<system>` tags,
delimiter breaks, role-play, system impersonation — which have no legitimate
reason to appear in data an agent retrieved, so one hit is enough to annotate.
Retrieved content is **annotated, never blocked**: blocking would let an attacker
DoS the agent by planting a trigger phrase in any page it reads.

**MCP caveat — do not overstate the win.** `MCPTool.action_category` /
`risk_tier` exist but are usually NULL, and NULL falls back to `"observe"`. For
untagged MCP tools the *category* rules therefore remain inert; what genuinely
landed is the kill switch and the audit trail. **Tagging the existing MCP tool
inventory is outstanding operational work.**

### Phase 2 — the core (2026-08-07)

| # | Change | Where |
|---|---|---|
| 2 | `degraded_reasons` tracks budget exhaustion, loop, truncation and tool errors; drives the episode `success` flag. 500-episode cap per agent | `internal_agent.py`, `episodic_memory.py` |
| 27 | Skill bodies over 1500 tokens become a manifest plus a `load_skill(skill_id)` tool; smaller sets stay inline | `internal_agent.py` |
| 17 | New `stream_chat_events()` streams with tools and reassembles tool-call deltas; every turn streams; the second call is gone | `llm_router.py`, `internal_agent._stream_turn` |
| 13 | `_resolve_tool` / `_execute_tool_call` split; governance moved into `_before_tool_hooks`; **pool tools now use the same gate** | `internal_agent.py` |
| 23/24 | `agent_run_events`: append-only, hash-chained per run, `tool_started` written **before** execution with a `replay` verdict | migration `032`, `models/run_event.py`, `services/run_event_log.py` |

**Why #17 cost more than estimated.** `stream_chat` does not accept tools, and
you cannot know which turn is the final one before making the call — so
"stream only the last turn" is not implementable. The only real fix is to stream
every turn and correctly reassemble tool calls that arrive in fragments.

**Why the gate had to move for pool tools.** Phase 1 left two gates (pool tools
inside `execute_tool`, everything else in `_dispatch`). Phase 2 unified them;
the pool branch now passes `governance=None` so the verdict is rendered once —
otherwise every gated call would be **audited twice and raise two approval
requests**.

### Phase 3 — orchestration (2026-08-07)

| # | Change | Where |
|---|---|---|
| 19 | Durable checkpointer: `AsyncPostgresSaver` in prod; `MemorySaver` under pytest | `app/core/graph_checkpoint.py` |
| 20 | `_approval_node` uses `interrupt()`; worker returns `waiting_approval`; resume via `Command` | `master.py`, `workers/tasks.py`, `routers/approval.py` |
| 18 | Back edges: validation → replan (capped); approval → re-execute or summarize / error | `master.py` |
| 21 | Real validation scoring (EN+ZH risk phrases, risk_score, action_items) | `app/agents/validation.py` |
| 22 | Removed unused `ToolNode`; surface `agent_run_events` into `state["loop_events"]` | `master.py` |
| 23 | `messages_json` append under `SELECT … FOR UPDATE` | `internal_agent.py`, `workers/tasks.py` |
| 24 | Startup recovery sweep logs interrupted runs | `run_recovery.py`, `main.py` lifespan |

**Why #20 before wiring `approval_required`.** Routing more traffic into a
blocking poll would exhaust the 4 API workers. After interrupt, wiring
`approval_required` into `_validation_decision` is safe and done.

**Resume path.** `POST /approvals/{id}/decide` records the decision then
dispatches `resume_master_agent_task` with `thread_id` from the approval
payload. The graph re-enters the approval node; `interrupt()` returns the
decision; approved runs with prior `needs_approval` tools re-dispatch with
`pre_approved=True`.

### Phase 4 — budgets, confidence, prompts (2026-08-07)

| # | Change | Where |
|---|---|---|
| 10 | `estimate_tool_confidence()` feeds gatekeeper | `tool_confidence.py`, `internal_agent._govern` |
| 4 | Default `tool_call_budget` tracks `max_steps` | `internal_agent.py` |
| 15 | Sequential execution for mutate/remediate/… categories | `internal_agent` dispatch |
| 16 | Budget/loop verdicts computed before any `await` | `internal_agent` dispatch |
| 28 | Prompt registry | `app/core/prompts.py` |
| 29 | Structured JSON `generate_summary` contract | `llm_router.py` |
| 6 follow-up | Mid-string injection screen on untrusted content only | `guardrails.py` |
| — | `AGENTS.md` project rules for coding agents | repo root |

### Post-review fixes (2026-08-07, same day)

A review of the phases-0-4 branch found the approval loop did not close. Five
fixes, all with regression tests:

| Symptom | Cause | Fix |
|---|---|---|
| Approving never let the action run — the graph re-dispatched, was refused again, and summarised itself | `pre_approved` was written into the executor context and state, but nothing ever read it | `AgentExecutor.execute` honours it for the high-permission gate (audited as `dispatch:pre_approved`); `InternalAgentRunner(pre_approved=…)` spends it on the **first** gated tool call only |
| A second gated action in the same run was waved through with no human | `_validation_decision` accepted any `approval_status == "approved"`, and that value persisted for the life of the thread | Decisions are scoped to an `approval_round`; the executor spends the decision and bumps the round, so the next gate must ask again (`_approval_is_current`) |
| Every approved run left a dangling **pending** approval row | `interrupt()` discards the node's writes, so the "create once" guard (`approval_record_id` in state) was always empty on resume | Idempotency moved to a deterministic per-round `request_id` (`approval_request_id()`, uuid5 — a suffix would overflow `String(36)`), looked up before creating |
| Every non-graph approval decision spawned a failing Celery resume + 2 retries | the decide endpoint resumed *all* approvals, falling back to `record.request_id` as a thread that was never suspended | `graph_resume_target()` — resume only `agent_execution` approvals that carry a `thread_id` |
| `state["loop_events"]` was unreachable (#22 only half-landed) | the runner never returned the `run_id` it logged under | `InternalAgentRunner.run_id` is returned with every result and streamed `done` event |

Also: the startup recovery sweep was a full scan of an append-only table on
every API worker boot — now windowed (`DEFAULT_RECOVERY_WINDOW_HOURS = 48`,
filtered in SQL); `generate_summary`'s plain-text fallback no longer re-sends
the whole request on a rate limit or a dropped connection
(`is_response_format_rejection`); `degraded_reasons` records each kind once.

**Corrected from the review:** `approval_requests.user_id` has no FK, so the
`user_id=0` sentinel in `_request_approval` inserts fine — no fix needed.

---

## Residual (not blocking)

- **#14** per-turn model adaptation (cheap recon → escalate on hit)
- **#26** provider `context_window` / pricing metadata → real compaction threshold
- **#5 ops** tag existing MCP tools so category rules are not inert
- **Evaluation** injection red-team corpus, prompt regression baseline
- **Supply chain** pinned deps, minimum release age, lockfile commit gate
- **UI** for interrupted runs / recovery report (the *recovery* report; the
  `waiting_approval` state itself is surfaced as of 2026-08-08)

### Verification debt (recorded 2026-08-08)

Named separately from the feature backlog because these are gaps in what has
been *proven*, not in what has been built.

- **No end-to-end run of the approval path.** Every test of it is mocked. The
  three layers never exercised together are a real LLM provider, a Celery
  worker, and the `AsyncPostgresSaver` checkpointer. The manual pass worth
  doing before this ships: submit a high-risk task → confirm the execution
  reports `waiting_approval` → approve it in the UI → confirm the action
  actually ran and the answer landed in the conversation. Then repeat with a
  run that hits a *second* gate, which is the case the round-scoping fixed.
- **No test runner in `webui/`.** No vitest/jest, no test files, no `test`
  script. Frontend changes are verifiable only by `tsc -b` and `eslint`, so
  the chat poller's `waiting_approval` handling has no regression test.
  `eslint src/pages/Chat.tsx` currently reports 16 pre-existing problems —
  that is the baseline to compare against, not a clean sheet.
- **The commit split is not per-commit green.** The 2026-08-07 work was split
  retroactively at file granularity and ordered by dependency; only the final
  tree is verified. `internal_agent.py` (+742) and `master.py` (+630) each
  span several phases and could not be split further without guessing which
  hunk belonged to which change.
- **`generate_summary` returns `str | dict`** with no annotation. One caller
  (`master._summarizer_node`) handles both.

### Repo hygiene (recorded 2026-08-08)

- **`.git/hooks/post-commit` runs `git push origin main`.** It pushes `main`
  regardless of the branch being committed, so it neither backs up the branch
  you are working on nor stays out of the way. It currently fails because the
  remote is ahead; if `main` ever becomes fast-forwardable it will start
  pushing unreviewed local `main` to the public repo on every commit. Local
  only — not in version control, so a fresh clone will not have it.
- **`.gitignore` ends with a blanket `*.png`.** Existing tracked assets
  (`webui/src/assets/hero.png`) are unaffected, but any *new* image asset is
  silently ignored. Probably meant to catch agent debug screenshots only.

---

## Verification method

Every delivered item has regression tests. Suite: 272 (2026-06-03) → 365
(pre-audit) → 477 (phases 0-2) → 498 (phases 0-4) → **518 passing** after the
post-review fixes, 59 files.
Alembic head: `032_agent_run_events` (+ LangGraph checkpoint tables via
`AsyncPostgresSaver.setup()`).

## Operational notes

- `alembic upgrade head` is required on deploy for `032_agent_run_events`.
- `AUTO_APPROVE` defaults to **false**; set `AUTO_APPROVE=true` in `.env` for
  local self-approve. Graph still creates the approval row then auto-decides.
- `GRAPH_CHECKPOINT_BACKEND=memory` forces in-process checkpointer (tests set
  this automatically via `PYTEST_CURRENT_TEST`).
- Production checkpointer uses psycopg against the same Postgres as the app
  (`DATABASE_URL` with `+asyncpg` stripped).
- The test database is shared and non-transactional; tests that query by
  `agent_id` must match on their own `run_id` rather than asserting row counts.
