---
name: streaming-internal-agent-design
description: Design for streaming a single internal sub-agent's output (final answer token stream + tool-call lifecycle events) over SSE, with a minimal Agents-page UI consumer.
type: spec
date: 2026-05-31
status: approved
---

# Streaming Internal Sub-Agent Output — Design

## Goal

Let a user run **one internal sub-agent** directly and watch it work live: the
final answer streams token-by-token, and each tool call surfaces as a
lifecycle event (`tool_call_start` → `tool_call_end`). Intermediate reasoning
text during tool steps is **not** streamed (out of scope by decision).

This is the "A 打底" foundation. Group-chat streaming (path B) and Celery
master-agent orchestration streaming (path C) are explicitly out of scope and
may build on this later.

## Key constraint that shapes the design

`LLMRouter.stream_chat()` (in `app/services/llm_router.py`) yields **text
deltas only** — it does not accept a `tools` parameter and ignores
`delta.tool_calls`. So for a tool-equipped agent, "offer tools / decide" and
"stream the answer" cannot happen in the same LLM call with today's router.

**Chosen approach (Approach 1): batch loop + streamed final synthesis.**
- The tool-call loop runs with batch `router.chat(tools=...)` exactly as today.
- Tool steps emit `tool_call_start` / `tool_call_end` SSE events around dispatch.
- When the model returns text-only (ready to answer), discard that batch text
  and re-issue the messages through `router.stream_chat()` (with `tools=None`)
  to stream the final answer token-by-token.
- Cost: a tool-equipped agent makes **one extra LLM call** on the final step
  (the discarded "decision" call). Accepted for interactive single-agent chat.
- Benefit: **zero router changes**, reuses the proven `stream_chat()` primitive,
  the tool loop logic is untouched, lowest risk.

Rejected Approach 2 (tool-aware streaming inside the router) avoids the extra
call but requires accumulating OpenAI tool_call deltas by index, handling
provider differences, and suppressing intermediate reasoning text the user
explicitly did not want — higher risk for no required benefit.

## Architecture

```
Browser (fetch + ReadableStream reader, like existing streamChat)
  → POST /api/v1/agents/{agent_id}/execute/stream
  → InternalAgentRunner.execute_stream()   (in-process async generator, no Celery)
      ├─ each tool step: batch router.chat(tools=...) → emit tool_call_start/end
      └─ final step: router.stream_chat(tools=None) → emit text deltas → done
```

In-process, same as `chat_stream.py`. Single-worker architecture means no
cross-process plumbing is needed.

### Endpoint

`POST /api/v1/agents/{agent_id}/execute/stream`

- Auth + guardrail identical to existing `POST /agents/{agent_id}/execute`:
  `require_permission(Permission.TASK_EXECUTE)`, `check_prompt_sync(task)` runs
  **before** the stream opens; a blocked prompt returns HTTP 400 (no stream).
- Request body: `{ "task": "<str>" }` (same shape as `/execute`), optionally
  `conversation_id` for memory continuity.
- Returns `StreamingResponse(media_type="text/event-stream")` with the same
  headers as `chat_stream.py`: `Cache-Control: no-cache`, `Connection:
  keep-alive`, `X-Accel-Buffering: no`.
- **kind branch:**
  - `internal` → true streaming via `execute_stream()`.
  - non-internal (`external`, openclaw, etc.) → run the existing batch
    `AgentExecutor().execute()` and emit its result as a single `done` event
    (or `error` on failure). The frontend then handles both kinds uniformly
    with no special-casing.

## Runner refactor (DRY)

`InternalAgentRunner` currently exposes `async def execute(task,
conversation_id, user_id) -> dict` containing the whole tool loop.

**Make `execute_stream()` the single canonical implementation; `execute()`
becomes a thin wrapper that drains it.**

```python
async def execute_stream(self, task, conversation_id, user_id) -> AsyncIterator[dict]:
    # Reuses: _build_system_prompt / _build_tools / _resolve_mcp_lookup
    #         / _load_memory / _maybe_compact / _dispatch / _append_memory
    yield {"type": "start", "agent_id": ..., "agent_name": ...}
    for step in range(self.max_steps):
        messages = await self._maybe_compact(messages, router)
        msg = await router.chat(messages, tools=tools or None, ...)   # batch, as today
        if text_only:
            # auto-continue nudge logic preserved (not emitted, not persisted)
            ...
            # final synthesis: re-stream
            async for delta in router.stream_chat(messages, ...):     # tools=None
                final_parts.append(delta)
                yield {"type": "text", "content": delta}
            final_text = "".join(final_parts)
            break
        for call in tool_calls:
            yield {"type": "tool_call_start", "name": ..., "arguments": ..., "call_id": ...}
        results = await asyncio.gather(*[self._dispatch(c) for c in tool_calls])
        for call, res in zip(tool_calls, results):
            yield {"type": "tool_call_end", "name": ..., "call_id": ...,
                   "result_preview": res[:200], "error": res.startswith("ERROR")}
    # error paths (LLM error / max steps) yield {"type": "error", ...} and return
    await self._append_memory(conversation_id, user_id, new_messages)   # same as execute()
    yield {"type": "done", "output": final_text, "execution_time": ..., "tool_calls": tool_call_log}

async def execute(self, task, conversation_id, user_id) -> dict:
    # drain execute_stream(), reassemble the legacy dict from start/text/done events
    ...
```

Requirements:
- **Behavior parity:** `execute()` reassembles the exact same dict shape it
  returns today (`status`, `output`, `agent_id`, `agent_name`, `execution_time`,
  `tool_calls`, and the failed/error variants). All existing callers
  (`AgentExecutor`, group chat) are unaffected.
- The auto-continue nudge (text-only-but-has-tools-and-never-used-one) stays in
  `execute_stream()`; nudges emit no SSE event and are not persisted, as today.
- The final re-stream call passes `tools=None` — this is Approach 1's one extra
  call.

## SSE event protocol

Wire format identical to `chat_stream`: each event is `data: {json}\n\n`.

| type | fields | when |
|------|--------|------|
| `start` | `agent_id`, `agent_name` | stream opens |
| `tool_call_start` | `name`, `arguments`, `call_id` | before each tool dispatch |
| `tool_call_end` | `name`, `call_id`, `result_preview` (≤200 chars), `error` (bool) | after each tool completes |
| `text` | `content` (delta) | final answer, token-by-token |
| `done` | `output` (full final text), `execution_time`, `tool_calls` (summary array) | normal completion |
| `error` | `content` | terminal failure |

## Error handling

- **LLM call error** (any loop step) → emit `error`, terminate, do **not**
  persist memory (matches today's `execute()` failed branch).
- **Tool dispatch error**: `_dispatch` already self-catches and returns an
  error string → surfaced via `tool_call_end` with `error=true` +
  `result_preview`; the loop **continues** so the agent can react, as today.
- **Max steps exceeded** → emit `error` (`exceeded tool_loop_max_steps`), no
  persistence, matches today.
- **Client disconnect** → generator is GC'd; persistence happens only on the
  successful path before `done`, so there is no half-written memory slice.
- **Guardrail block** → HTTP 400 before the stream opens, like `chat_stream`.
- **external/non-internal agent** → batch `execute()` exception is wrapped as a
  single `error` event.

## Frontend (scope b — minimal consumer)

- **API client** (`webui/src/api/client.ts`): add `executeAgentStream(agentId,
  task, onEvent)` following the existing `streamChat` pattern (`fetch` +
  `ReadableStream` reader + SSE line buffering), dispatching parsed events to a
  callback.
- **Agents page** (`webui/src/pages/Agents.tsx`): add a "运行 / 测试" panel for a
  selected agent:
  - task input + run button,
  - a live transcript area that renders:
    - tool steps as timeline entries (`tool_call_start` → spinner;
      `tool_call_end` → ✓/✗ with `result_preview`),
    - the final answer accumulating from `text` deltas,
  - terminal state from `done` / `error`.
- Keep it minimal and consistent with existing Agents.tsx styling; no new
  routing or global state.

## Testing

Unit tests follow `tests/test_internal_agent.py` patterns (mock router; memory
persistence needs the test DB).

- `execute_stream` — no-tool agent: emits `start` → `text*` → `done`.
- `execute_stream` — tool agent: emits `start` → `tool_call_start` →
  `tool_call_end` → `text*` → `done`; asserts the tool was dispatched and the
  memory slice was persisted.
- `execute_stream` — LLM raises mid-loop: emits `error`, no persistence.
- **`execute()` parity test**: the wrapper's reassembled dict matches the
  legacy contract for both a tool and a no-tool path — protects every existing
  caller.
- Endpoint SSE smoke test: one happy-path internal-agent stream returns
  `text/event-stream` and a terminal `done`.

## Out of scope

- Group-chat live streaming (path B).
- Celery master-agent orchestration streaming (path C).
- Streaming intermediate reasoning text during tool steps.
- Extending the router for tool-aware streaming (Approach 2).
