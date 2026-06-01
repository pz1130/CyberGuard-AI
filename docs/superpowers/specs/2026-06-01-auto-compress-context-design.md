# Auto-Compress Long Conversation History — Design

**Date:** 2026-06-01
**Status:** Approved (brainstorming)
**Area:** `app/core/context_compressor.py` (new), `app/agents/master.py`, `app/config.py`, `tests/test_context_compressor.py` (new)

## Problem

Long-running agent sessions accumulate a `conversation_history` that grows
unboundedly across turns. Today the only mitigation is a naive sliding window
in `app/workers/tasks.py:323` ("Keep at most 20 messages / 10 turns"), which
discards context indiscriminately and causes the model to lose awareness of
earlier goals, decisions, and constraints.

The internal-agent ReAct loop already has its own per-step truncation and
prompt-based summary (`app/services/internal_agent.py:304, 359`), but that
path is intra-iteration. What is missing is **per-turn, history-level
compression** that runs before the master agent dispatches the user's
message to the LLM.

## Goal

Before each user turn is sent to the LLM, if the cumulative
`conversation_history` exceeds a configurable token threshold, replace the
history with a single summary message plus the most recent K messages. The
turn proceeds normally; the user sees no change.

## Non-goals

- No new dependency (no tiktoken, no langchain compressors).
- No change to the LLM router, guardrails, master agent state machine, or DB
  schema.
- No change to `internal_agent.py`'s intra-loop truncation/summary (already
  covered; different scope).
- No change to `_summarizer_node` (post-response condensation; different
  purpose).
- No DB persistence of summaries — they are in-memory representations for
  the current turn only. The full untruncated message log is still written
  to `Conversation.message` as today, so audit and the WebUI chat view are
  unaffected.

## Design decisions (locked in brainstorming)

- **What to compress:** long conversation history (not tool results, not
  attachments, not single-message payloads).
- **Where to compress:** cross-turn session history at the master-agent
  entry point (not inside the ReAct loop).
- **Trigger:** threshold-based, default 8000 tokens, env-configurable.
- **History replacement:** one summary message (system role) + the most
  recent K messages (default K=6, env-configurable).
- **Token estimation:** `len(text) // 4` per message, summed. Slightly
  conservative for CJK content; acceptable given we only need to know
  "are we over the threshold," not a precise count.

## Architecture

A single new module `app/core/context_compressor.py` provides four
functions:

1. `estimate_tokens(messages) -> int`
   Pure, sync. `sum(len(m["content"]) for m in messages) // 4`. Treats
   `messages` as `Iterable[Mapping[str, str]]`; tolerates missing/non-string
   content by coercing via `str()`.

2. `select_window(messages, summary, keep_last) -> list[dict]`
   Pure, sync. Returns `[summary_message] + messages[-keep_last:]` if
   `summary` is non-empty; otherwise `messages[-keep_last:]`. `keep_last <= 0`
   returns `[summary_message]` only. Caller is responsible for picking a
   sensible `keep_last`.

3. `compress_history(history, llm_router, *, max_tokens, keep_last) -> tuple[list, str | None]`
   Async core orchestrator. Returns `(new_history, summary_str)`. If
   `estimate_tokens(history) < max_tokens`, returns `(history, None)`
   without calling the LLM. Otherwise calls
   `llm_router.chat(messages=[_SUMMARY_PROMPT, user_history_as_user_msg])`
   exactly once, then `select_window(history, summary, keep_last)`.

4. `maybe_compress(history, llm_router, *, max_tokens=None, keep_last=None) -> tuple[list, bool, bool]`
   The hook callers use. Reads `CONTEXT_COMPRESS_MAX_TOKENS` and
   `CONTEXT_COMPRESS_KEEP_LAST` from `app.config.settings` when the kwargs
   are not passed. Returns `(new_history, compressed: bool, degraded: bool)`.
   - `degraded=True` means the LLM call failed and we fell back to the
     sliding window so the turn can still proceed.
   - `degraded=True, compressed=True` is impossible: degraded always
     means "LLM unavailable, we used keep_last tail only."

### Summary prompt

A module-level constant `_SUMMARY_PROMPT` (Chinese, project style) instructs
the LLM to emit a structured digest:

> 你是会话历史压缩器。请把以下对话压缩为结构化要点(中文, ≤ 600 字):
>
> 1. 用户目标与已确认事实
> 2. 待办 / 未决问题
> 3. 关键引用(原文短语)
> 4. 不确定 / 已废弃的想法
>
> 输出纯文本,不要使用 markdown / 列表前缀 / 标题。

The historical messages are passed as a single `user` role message with
each line `[role] content` so the model can see role boundaries.

### Error handling

- **LLM call raises** (timeout, rate limit, provider error):
  `log.warning("context_compressor: LLM call failed; degrading to sliding
  window: %s", exc)`; return `select_window(history, "", keep_last)` with
  `degraded=True`. The turn proceeds; no 5xx propagates to the user.
- **`llm_router is None`** (no provider configured) and threshold exceeded:
  same degraded path — never block a turn on missing LLM config.
- **Empty history:** `estimate_tokens` returns 0, `maybe_compress` is a
  no-op.
- **Single message that alone exceeds `max_tokens`:** we do not split
  individual messages. The summary still runs over the full history; the
  LLM may not perfectly digest a 50KB paste, but that is a known limitation
  already partially mitigated by `internal_agent._truncate_tool_result`
  for tool outputs.

### Integration point

`app/agents/master.py` around line 523, where the master assembles
`messages` for the LLM call. Insert a single hook between reading history
from state and extending `messages`:

```python
history = state.get("conversation_history") or []
history, _compressed, _degraded = await maybe_compress(history, self.llm_router)
# Optional: state["context_compression"] = {"compressed": _compressed, "degraded": _degraded}
messages: List[Dict[str, str]] = [
    {"role": "system", "content": system_prompt}
]
messages.extend(history)
messages.append({"role": "user", "content": user_input})
```

`_compressed` / `_degraded` are not consumed in the first cut; they are
returned so future work (logging, metrics, surfacing a "history was
summarized" hint) can wire them in without an API change.

## Data flow

1. User sends turn N. Master agent reads `state["conversation_history"]`
   (the full untruncated log from `Conversation.message`).
2. `maybe_compress` is invoked. If under threshold → history unchanged.
3. If at/over threshold → one LLM call summarises the history; the new
   in-memory `history` is `[summary] + last K`.
4. Master agent dispatches to the LLM with the new history.
5. After the LLM responds, normal turn-completion path persists the full
   user + assistant turn to DB. No summary is persisted.

## Configuration

Two new settings in `app/config.py`:

- `context_compress_max_tokens: int = 8000`
- `context_compress_keep_last: int = 6`

Both are read via the same `app.config.settings` singleton used elsewhere;
no new env-var conventions are needed (Pydantic will read
`CONTEXT_COMPRESS_MAX_TOKENS` / `CONTEXT_COMPRESS_KEEP_LAST` from env).

## Testing

`tests/test_context_compressor.py` — pure-function unit tests, no DB, no
real LLM, no fixture files:

- `estimate_tokens`:
  - empty list → 0
  - `[{role:user, content:"abc"}]` → 0 (3 // 4)
  - `[{role:user, content:"x"*401}]` → 100
  - CJK content counted as chars (4-char "你好世界" → 1 token)
  - non-string content coerced via `str()` without raising
  - missing `content` key treated as 0 length

- `select_window`:
  - `len(history) <= keep_last` → unchanged
  - `len(history) > keep_last`, summary present → `[summary] + tail`
  - `len(history) > keep_last`, summary empty/missing → `tail` only
  - `keep_last=0`, summary present → `[summary]` only
  - `keep_last=0`, summary empty → `[]`

- `maybe_compress` (with `AsyncMock` for `llm_router`):
  1. Below threshold → `llm_router.chat` not called, returns
     `(history, False, False)`.
  2. At threshold → `llm_router.chat` called exactly once; returns
     `(new_history, True, False)`; new_history has `len == 1 + keep_last`.
  3. LLM raises → returns `([...tail], False, True)`; tail length is
     `keep_last`.
  4. `llm_router is None`, at threshold → returns
     `([...tail], False, True)`; no exception.
  5. Empty history → returns `([], False, False)` without calling LLM.

A single optional smoke assertion is added to the existing master-agent
test path (only when `MASTER_AGENT_MODEL` is configured) confirming that
the LLM call receives a `system` summary message as the first history
entry when fed a long history. It is guarded behind a `pytest.mark.skipif`
on missing config so CI does not require a live provider.

## Cross-cutting

- **No DB migration.** DB schema and the `Conversation.message` write path
  are untouched.
- **No frontend change.** The chat view always renders the untruncated
  stored messages.
- **No worker change.** This runs in the master agent at the start of each
  turn, which is already in-process with the API request.
- **Backwards compatible.** When `CONTEXT_COMPRESS_MAX_TOKENS=0`, the
  feature is effectively disabled (`0 < threshold` is always false → no
  compression, no LLM call).

## Risks

- **LLM cost:** one extra small chat completion per compressed turn. The
  completion uses the configured master-agent model; the summary prompt
  is ~80 tokens input + ~600 tokens output worst case.
- **Latency:** +1-2s on compressed turns. Negligible vs. the multi-second
  agent runs these turns are part of.
- **Summary quality:** a long, complex history may be imperfectly
  summarised. The `keep_last=6` tail preserves immediate context. Users
  who need to refer to far-back details can restate them; this is the
  same tradeoff every summarising chat product makes.
- **Threshold tuning:** 8000 is a reasonable default for `gpt-4o`-class
  models with 128K context. Operators with smaller-context models should
  set `CONTEXT_COMPRESS_MAX_TOKENS` to a value safely below the model's
  context window minus the system prompt + this-turn reserve.
