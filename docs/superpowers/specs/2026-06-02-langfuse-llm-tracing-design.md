# Langfuse LLM Tracing

**Date:** 2026-06-02
**Status:** Approved → implementation
**Branch / PR:** `feat/langfuse-llm-tracing` (PR #8)

## Motivation

Borrowed from PentAGI's Langfuse integration. We already have OpenTelemetry
spans + `token_usage_service`, but no **per-conversation / per-agent LLM trace
visualization**: prompts, completions, model, token usage, and cost grouped by
session and agent. Langfuse (self-hosted) fills that gap and is invaluable for
debugging multi-agent chains. This adds a thin, optional Langfuse layer that is
a clean no-op until configured.

## Decisions (from brainstorming)

- **Integration:** Langfuse SDK with **manual generations** created inside the
  LLM router (explicit, testable, full control). Not the OpenAI drop-in, not
  OTLP export.
- **Content:** send **full prompts + completions** (gated behind Langfuse env
  config; nothing leaves the process unless a self-hosted instance is wired up).
  No redaction in v1.
- Coexists with the existing OTel tracing — independent and additive.

## Architecture

### New module: `app/core/langfuse_tracing.py`

Mirrors `app/core/telemetry.py`'s "no-op when unconfigured" pattern.

- `setup_langfuse() -> None` — initialise the Langfuse client iff
  `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` are all set;
  otherwise leave the module client `None`. Lazy `import langfuse` so a missing
  dependency logs a warning and disables tracing instead of breaking startup.
  Idempotent.
- `TraceContext` dataclass: `session_id, user_id, agent_name, tags`.
- A module-level `ContextVar[Optional[TraceContext]]`.
- `trace_run(*, session_id, agent_name=None, user_id=None, tags=None)` — a
  context manager that sets the contextvar (resetting on exit) and, when the
  client is live, opens a Langfuse trace/span carrying `session_id` and
  `user_id` so nested generations group per conversation and tag per agent.
  No-op (still sets the contextvar) when the client is `None`.
- `record_generation(*, name, model, input, output, usage=None, provider=None,
  metadata=None) -> None` — reads the contextvar and creates one Langfuse
  generation with input/output/model/usage/session/agent. No-op if the client
  is `None`. **All SDK-version-specific calls live here** (isolated + mockable).
- `flush_langfuse()` / `shutdown_langfuse()` — flush the async batch on shutdown.

### Router integration (`app/services/llm_router.py`)

Emit exactly one generation at each LLM choke point that has input + output +
usage, beside the existing `_record_token_usage(...)` call (reusing
`response.usage`):

- `chat` (line ~639)
- `parse_intent` (line ~559)
- `generate_summary` (line ~708)
- `stream_chat` — accumulate streamed deltas, record on completion.

Each is a single `record_generation(...)` call. No behaviour change when
Langfuse is unconfigured.

### Session / agent context plumbing

Wrap execution entry points with `trace_run(...)` so the contextvar is populated
before any router call:

- `internal_agent.execute` / `execute_stream` →
  `agent_name=self.agent_name, user_id, session_id=conversation_id`
- master agent run (`MasterAgent`) → `session_id=request_id`,
  `agent_name="master"`
- `/chat` and `/chat/stream` routers → `session_id=conversation_id, user_id`

No public signatures change (contextvar, not new parameters). Nested
`trace_run` calls (e.g. master → internal agent) keep the inner agent's name
while sharing the conversation session.

### Lifecycle

- Call `setup_langfuse()` at FastAPI startup, next to `setup_telemetry()`.
- Call `flush_langfuse()` on FastAPI shutdown (the SDK batches asynchronously).

## Data flow

```
entry point (chat router / agent executor / master)
  → trace_run(session_id=conversation, agent_name=...)   # sets contextvar + Langfuse trace
    → llm_router.chat()/parse_intent()/...               # one or many LLM calls
      → OpenAI response (+ usage)
      → record_generation(name, model, input, output, usage)   # nested generation
  → trace_run exits (reset contextvar, generations grouped under the session)
```

## Error handling

- Unconfigured (missing env or missing `langfuse` package): every entry point is
  a no-op; zero overhead beyond a cheap contextvar set.
- `record_generation` / `trace_run` swallow Langfuse SDK errors (log at debug)
  so tracing never breaks an LLM call or an agent run.
- Existing OTel spans and `token_usage_service` are unchanged.

## Configuration / dependencies

- Env: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.
- Add `langfuse` to `pyproject` (lazy import; graceful if absent).

## Testing (mocked client — no network)

- `langfuse_tracing`:
  - `record_generation` builds a generation with the expected fields
    (session_id, agent, model, input, output, usage) from the contextvar.
  - no-op when the client is `None` (records nothing, raises nothing).
  - `trace_run` sets the contextvar inside the block and resets it after.
- `llm_router`:
  - with a mocked Langfuse client + an active `trace_run`, `chat` records a
    generation carrying the contextvar's session/agent and the call's
    input/output.

## Out of scope (YAGNI for v1)

- Cost dashboards, eval scoring, prompt management (Langfuse UI provides views).
- Content redaction (full content per decision).
- Tracing non-LLM spans (OTel already covers HTTP/DB/Celery).
- OpenAI drop-in wrapper or OTLP-to-Langfuse export.
