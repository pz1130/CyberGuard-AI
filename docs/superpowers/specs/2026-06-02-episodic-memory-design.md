# Episodic Memory (success reuse)

**Date:** 2026-06-02
**Status:** Approved → implementation
**Branch / PR:** `feat/episodic-memory` (PR #9)

## Motivation

Borrowed from PentAGI's episodic memory. Today the agent's only durable memory
is RAG over uploaded documents (`knowledge_service`). It does not learn from its
own runs. Episodic memory records **which approach succeeded for which task** and
recalls similar past successes to prime future runs, so repeated-type tasks get
better over time.

## Decisions (from brainstorming)

- **Scope:** episodic memory only. The `context_compressor` section/QA-pair
  strategy tweak is deferred to a separate follow-up.
- **Storage:** a dedicated `agent_episodes` table (not a reused KB).
- **Distillation:** heuristic, **no extra LLM call** — approach = ordered tool
  names, outcome = truncated final answer.
- **Write policy:** record **successful runs only** (`status == "completed"`).
- **Opt-in** per agent via `metadata_json.enable_episodic`.
- Recall is scoped **per agent**.

## Architecture

### New table + migration: `agent_episodes` (`017_agent_episodes`, after `016_ocr`)

Columns:
- `id` PK
- `agent_id` int (the internal agent's id; indexed)
- `task_text` Text — the task this episode is about
- `task_embedding` `vector(1536)` — embedding of `task_text` (text-embedding-3-small)
- `approach` Text — distilled "what was done" (ordered tool names)
- `outcome` Text — truncated final answer summary
- `success` Boolean, default true
- `tool_count` int
- `created_at` timestamp (naive, project convention)
- `metadata_json` JSON nullable

Indexes: btree on `agent_id`; HNSW on `task_embedding` (`vector_cosine_ops`,
m=16, ef_construction=64) — mirrors `003_pgvector_knowledge`. Pinned to **1536
dim** (single vector column, no multi-dim routing).

Migration style follows `003_pgvector_knowledge.py` (raw `op.execute` for the
`vector` column + HNSW index; `CREATE EXTENSION IF NOT EXISTS vector` is a
no-op since pgvector is already installed). **Note:** cannot be executed in the
local dev environment (no Postgres here); it is code-reviewed, and applied by
the normal startup/CI `alembic upgrade head`.

### New service: `app/services/episodic_memory.py`

- `EpisodicMemoryService`:
  - `async record(db, *, agent_id, task, approach, outcome, success=True,
    tool_count=0, embedding=None) -> None` — embeds `task` (or reuses a supplied
    `embedding`) and inserts a row. **Best-effort:** on embed/DB failure, log and
    skip; never raises.
  - `async recall(db, *, agent_id, task, top_k=3) -> tuple[list[dict], list[float] | None]`
    — embeds `task`, runs the same ANN cosine SQL as `knowledge_service.query`
    scoped to `agent_id` and `success = true`, returns `(episodes, embedding)`.
    The embedding is returned so the caller can reuse it at `record` time
    (avoids a second embed call). On embed failure returns `([], None)`.
  - Embeddings via `router.embed(model="text-embedding-3-small",
    provider_id=...)`. Reuses the raw `::vector(1536)` ANN pattern.
- `get_episodic_memory_service()` singleton.
- `distill_approach(tool_call_log) -> str` — pure helper: ordered, de-duplicated
  tool names joined by `→` (e.g. `web_search→vuln_search→kb_search`).

### Internal-agent integration (`internal_agent.py`)

- New flag `enable_episodic` (from `metadata_json.enable_episodic` or a
  top-level key), parsed like `enable_search`.
- **Recall (read):** in `_build_system_prompt`, when enabled, recall top-k
  similar past successes for `(agent_id, task)` and append a
  `## 过往成功经验（参考）` section listing `task → approach → outcome`. The
  returned embedding is stashed on `self._episode_embedding` for reuse.
  - `_build_system_prompt` currently takes no task; it will accept the task
    text (recall needs it). Callers in `_run_loop` pass `task`.
- **Record (write):** in `execute` (batch) and `execute_stream`, on a
  `completed` / `done` result only, build `approach = distill_approach(log)`,
  `outcome = truncated final output`, and call `record(...)` reusing
  `self._episode_embedding`. No extra LLM call.
- A thin module-level `episodic_memory` adapter opens `AsyncSessionLocal`
  internally (mirrors the `knowledge_service` adapter), monkeypatchable in
  tests via `app.services.internal_agent.episodic_memory`.

## Data flow

```
run start → _build_system_prompt(task)
  → episodic_memory.recall(agent_id, task)        # embeds task once
    → ANN cosine over agent_episodes (success=true, agent scoped)
  → inject "## 过往成功经验" into system prompt
… tool loop runs …
run end (completed) → execute()/execute_stream()
  → distill_approach(tool_call_log) + truncate(output)
  → episodic_memory.record(agent_id, task, approach, outcome, embedding=reused)
```

## Error handling

- All episodic operations are best-effort and individually wrapped: an embed
  error (e.g. provider lacks embeddings), a DB error, or a missing table never
  breaks the agent run — they log at warning/debug and the run proceeds.
- Disabled agents pay zero cost (flag check short-circuits before any embed/DB).

## Testing (mocked — no Postgres required)

- `episodic_memory`:
  - `distill_approach` builds the ordered, de-duplicated tool string.
  - `recall` issues the agent-scoped, success-filtered ANN query (fake `db`
    with an `AsyncMock` `execute`; fake embed) and returns `(episodes, embedding)`.
  - `record` inserts a row with the expected fields (fake `db`); reuses a
    supplied embedding without re-embedding.
  - embed failure → `recall` returns `([], None)`, `record` is a no-op.
- `internal_agent`:
  - recall text injected into the system prompt when `enable_episodic`.
  - `record` called with the tool-sequence approach on a completed run; reuses
    the recall embedding.
  - neither recall nor record fires when disabled.

## Out of scope (YAGNI for v1)

- Auto-pruning / TTL / size caps (add later if the table grows).
- Recording failures / negative examples.
- LLM-distilled "lessons".
- Cross-agent or global episode sharing.
- `context_compressor` strategy changes (separate follow-up).
- A WebUI for browsing episodes.
