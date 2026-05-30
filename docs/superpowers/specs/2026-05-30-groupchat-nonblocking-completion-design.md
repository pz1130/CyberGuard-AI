# Non-blocking group-chat completion

**Date:** 2026-05-30
**Status:** Approved — ready for implementation plan

## Background

A `POST /api/v1/groupchat/sessions/{id}/complete` request ran the *entire*
multi-round, multi-agent discussion synchronously inside the HTTP request. The
API runs as a **single uvicorn worker** (`CMD uvicorn app.main:app` — no
`--workers`), so the long-running request monopolised the lone asyncio event
loop and starved every other request — including login.

This was first observed as an infinite busy-loop (a concurrent `load_session()`
swapped the in-memory session object out from under `run_to_completion`, freezing
its loop counter). That specific defect was fixed separately (re-read the live
session each iteration + honour `run_round`'s `max_rounds_reached`; `load_session`
returns the live in-memory object instead of clobbering it). This spec addresses
the **architectural** hazard that remains: a legitimately long discussion
(`max_rounds` × N agents × LLM latency, each external agent waiting up to
`SUB_AGENT_TIMEOUT`) still ties up the single worker for minutes.

## Goal

`/complete` must not block. Dispatch the discussion as a background task on the
existing event loop, return immediately, and let the frontend poll for progress.
A long — or wedged — discussion can then never block request handling.

## Non-goals

- No Celery offload, no multi-worker, no cross-process/Redis-authoritative state.
  Those were considered and explicitly deferred (chosen approach: low-risk,
  in-process). Session state stays in-process memory + Redis as today, so the
  existing `load_session` "prefer in-memory" behaviour remains valid.

## Design

### 1. `GroupChatService` — `app/services/group_chat.py`

- Add `self._completion_tasks: Dict[str, asyncio.Task] = {}`.
- `start_completion(session_id) -> snapshot`: **idempotent**. If a task is already
  running for this session, do nothing and return the current snapshot. This also
  structurally prevents the concurrent double-`/complete` that triggered the
  original desync. Otherwise:
  `self._completion_tasks[session_id] = asyncio.create_task(self._run_completion_safe(session_id))`
  and return the current snapshot.
- `_run_completion_safe(session_id)`: wrap `run_to_completion` in `try/except`:
  - On exception: log a warning and append a `system` message
    (`"⚠️ Group chat run failed: <err>"`) to the session so the failure is
    visible to the operator.
  - `finally`: `self._completion_tasks.pop(session_id, None)` so `running` always
    flips back to false even on crash.
- In `run_to_completion`'s loop body add `await asyncio.sleep(0)` once per
  iteration — belt-and-suspenders so any future CPU-heavy round still yields the
  event loop.
- `cancel_session(session_id)`: in addition to setting `status="cancelled"`,
  cancel the background task if present (`task.cancel()`), then drop the handle.
- Define "running" as `session_id in self._completion_tasks`. Expose via a small
  helper `is_running(session_id) -> bool`.

### 2. Router — `app/routers/groupchat.py`

- `POST /sessions/{id}/complete`: load session (404 if missing), call
  `service.start_completion(id)`, return the session snapshot **immediately** with
  `running=True`. No longer awaits the discussion.
- `GET /sessions/{id}`: populate `running=service.is_running(id)` in the response.

### 3. Schema — `app/schemas/groupchat.py`

- Add `running: bool = False` to `GroupChatSessionResponse`.

### 4. Frontend — `webui/src/pages/GroupChat.tsx`

- Replace the single blocking `await api.runGroupChatComplete(id)` with:
  1. `await api.runGroupChatComplete(id)` (now returns immediately).
  2. Poll `api.getGroupChatSession(id)` every ~2 s, calling `setSession` each tick,
     until `running === false`.
  3. Stop polling and render the final transcript.
- Apply to both entry points: the create-and-run path and the standalone
  "complete" button. Show the existing `Round x/y` progress + spinner while
  `running`. Guard the poller against component unmount (clear interval / abort).
- `api.getGroupChatSession` / `runGroupChatComplete` response typing gains the
  optional `running` field.

## Data flow

```
create (fast, sync)
  -> POST /complete  -> start_completion -> create_task; return {running:true}
       background task: run rounds, persist memory+Redis each round,
                        status -> "completed", finally clear _completion_tasks
  -> frontend polls GET /sessions/{id} every ~2s
       running:true ... running:false (+ status completed) -> render transcript
```

## Error handling

| Case | Behaviour |
|------|-----------|
| Background task raises | Logged; `system` error message appended; `finally` clears task → `running:false` → frontend stops polling |
| Second `/complete` while running | No-op (idempotent) — prevents the original incident trigger |
| Cancel during run | `status="cancelled"` + `task.cancel()`; loop already checks `status=="active"` |
| Task dies unexpectedly | `finally` always clears handle → `running:false` → frontend stops |

## Testing

- `start_completion` returns immediately; background run drives `status -> completed`
  and clears `running` (await the stored task in the test).
- `start_completion` is idempotent while running — calling twice starts only one
  task (regression guard for the original incident).
- `cancel_session` stops an in-flight run and clears `running`.
- Existing `run_to_completion` regression tests stay green (the `sleep(0)` yield
  does not change logic).

## Files touched

- `app/services/group_chat.py`
- `app/routers/groupchat.py`
- `app/schemas/groupchat.py`
- `webui/src/pages/GroupChat.tsx`
- `tests/test_group_chat_completion.py` (extend)
