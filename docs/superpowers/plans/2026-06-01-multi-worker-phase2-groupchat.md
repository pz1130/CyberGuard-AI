# Multi-Worker Phase 2 — Group Chat → Redis + Celery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make group-chat completion cross-worker-safe by running it as a Celery task (not an in-process `asyncio.create_task`), guarding it with a Redis `SET NX` lock, serving `is_running`/cancel from Redis, and making `load_session` read Redis authoritatively.

**Architecture:** A `/complete` request acquires a Redis run-lock (`groupchat:lock:<id>`, `SET NX EX`) and, if acquired, dispatches `run_group_chat_completion_task(session_id)` to Celery; if the lock is held it is a no-op. The Celery task loads the session from Redis, runs `run_to_completion` (which persists each round back to Redis), then releases the lock. `is_running` checks the lock; cancellation writes a Redis cancel flag (`groupchat:cancel:<id>`) that the loop polls each iteration (a dedicated flag, never overwritten by the task's own persist). API polls read fresh session state via a now-Redis-authoritative `load_session`.

**Tech Stack:** Python 3.11, Celery (`@shared_task` + `asyncio.run`), `redis.asyncio` (via `app/core/redis_client.get_redis` / `cache`), `pytest` + `pytest.mark.asyncio` (matching `tests/test_group_chat_completion.py`).

**Scope note:** Phase 2 of the multi-worker unblock (spec: `docs/superpowers/specs/2026-06-01-multi-worker-unblock-design.md`). Shippable on its own and safe under single-worker. Depends on no other phase. The multi-worker flip is Phase 4.

**Why `load_session` becoming Redis-authoritative is now safe:** The original hang-fix kept in-memory authoritative because a concurrent `load_session()` could swap the session object *in the same process* while `run_to_completion` looped. Once completion runs in Celery, the loop (Celery worker) and the polls (API workers) are in **different processes**, each `GroupChatService` instance isolated. No in-process swap can occur, so API-side `load_session` can safely read fresh Redis state.

**Run tests with:** `python -m pytest tests/test_group_chat_multiworker.py tests/test_group_chat_completion.py -v` (Redis and Celery are faked/mocked; no external services).

---

## File Structure

- `app/services/group_chat.py` — **modify.** Add Redis run-lock + cancel-flag primitives; make `is_running` async (Redis); make `load_session` Redis-authoritative; refactor `start_completion` to dispatch Celery under the lock; have `run_to_completion` poll the cancel flag; rewrite `cancel_session`; delete `_completion_tasks` / `_run_completion_safe`.
- `app/workers/tasks.py` — **modify.** Add `run_group_chat_completion_task` + its async helper.
- `app/routers/groupchat.py` — **modify.** `await` the now-async `is_running`.
- `tests/test_group_chat_multiworker.py` — **new.** Lock, dispatch, cancel-flag, authoritative-load tests with a fake Redis.

---

## Task 1: Redis run-lock + cancel-flag primitives; async `is_running`

**Files:**
- Modify: `app/services/group_chat.py`
- Test: `tests/test_group_chat_multiworker.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_group_chat_multiworker.py`:

```python
"""Multi-worker safety tests for group chat (Redis lock / cancel flag / dispatch)."""
import pytest

import app.services.group_chat as gc
from app.services.group_chat import GroupChatSession, GroupChatMessage


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    async def exists(self, k):
        return 1 if k in self.store else 0

    async def delete(self, k):
        return 1 if self.store.pop(k, None) is not None else 0

    async def get(self, k):
        return self.store.get(k)


def _make_session(session_id, *, current_round=0, max_rounds=3, status="active"):
    s = GroupChatSession(
        session_id=session_id, user_id=1, agent_ids=[1, 2],
        max_rounds=max_rounds, current_round=current_round, status=status,
    )
    s.messages.append(GroupChatMessage(role="user", content="hi"))
    return s


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()

    async def _getter():
        return r

    monkeypatch.setattr(gc, "get_redis", _getter)
    return r


@pytest.mark.asyncio
async def test_run_lock_is_exclusive(fake_redis):
    svc = gc.GroupChatService()
    assert await svc.acquire_run_lock("s1") is True
    assert await svc.acquire_run_lock("s1") is False
    assert await svc.is_running("s1") is True
    await svc.release_run_lock("s1")
    assert await svc.is_running("s1") is False


@pytest.mark.asyncio
async def test_cancel_flag_round_trips(fake_redis):
    svc = gc.GroupChatService()
    assert await svc._is_cancelled("s1") is False
    await svc._set_cancel_flag("s1")
    assert await svc._is_cancelled("s1") is True
    await svc._clear_cancel_flag("s1")
    assert await svc._is_cancelled("s1") is False


@pytest.mark.asyncio
async def test_is_running_false_when_redis_down(monkeypatch):
    async def _broken():
        raise ConnectionError("down")
    monkeypatch.setattr(gc, "get_redis", _broken)
    svc = gc.GroupChatService()
    assert await svc.is_running("s1") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_group_chat_multiworker.py -v`
Expected: FAIL — `AttributeError: 'GroupChatService' object has no attribute 'acquire_run_lock'` (and `get_redis` not importable from `gc`).

- [ ] **Step 3: Add the lock/flag primitives and async `is_running`**

In `app/services/group_chat.py`, change the import line:
```python
from app.core.redis_client import cache
```
to:
```python
from app.core.redis_client import cache, get_redis
```

Add these module-level constants and helpers just above `class GroupChatService:`:
```python
_RUN_LOCK_TTL = 3600  # seconds; a completion run must never exceed this


def _lock_key(session_id: str) -> str:
    return f"groupchat:lock:{session_id}"


def _cancel_key(session_id: str) -> str:
    return f"groupchat:cancel:{session_id}"
```

Inside `GroupChatService`, replace the existing `is_running` method:
```python
    def is_running(self, session_id: str) -> bool:
        """Whether a background completion run is in flight for this session."""
        return session_id in self._completion_tasks
```
with:
```python
    async def acquire_run_lock(self, session_id: str) -> bool:
        """Acquire the cross-worker run lock. True if acquired, False if held."""
        try:
            r = await get_redis()
            acquired = await r.set(_lock_key(session_id), "1", nx=True, ex=_RUN_LOCK_TTL)
            return bool(acquired)
        except Exception:
            return False

    async def release_run_lock(self, session_id: str) -> None:
        try:
            r = await get_redis()
            await r.delete(_lock_key(session_id))
        except Exception:
            pass

    async def is_running(self, session_id: str) -> bool:
        """Whether a completion run holds the lock (cross-worker)."""
        try:
            r = await get_redis()
            return bool(await r.exists(_lock_key(session_id)))
        except Exception:
            return False

    async def _set_cancel_flag(self, session_id: str) -> None:
        try:
            r = await get_redis()
            await r.set(_cancel_key(session_id), "1", ex=_RUN_LOCK_TTL)
        except Exception:
            pass

    async def _clear_cancel_flag(self, session_id: str) -> None:
        try:
            r = await get_redis()
            await r.delete(_cancel_key(session_id))
        except Exception:
            pass

    async def _is_cancelled(self, session_id: str) -> bool:
        try:
            r = await get_redis()
            return bool(await r.exists(_cancel_key(session_id)))
        except Exception:
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_group_chat_multiworker.py -v`
Expected: PASS (3 tests). The `_completion_tasks` dict still exists for now (removed in Task 3); that's fine.

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_multiworker.py
git commit -m "feat(group_chat): add Redis run-lock + cancel-flag primitives, async is_running"
```
(a git hook may auto-push; expected.)

---

## Task 2: Make `load_session` Redis-authoritative

**Files:**
- Modify: `app/services/group_chat.py` (`load_session`)
- Test: `tests/test_group_chat_multiworker.py` (add a test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_group_chat_multiworker.py` (before nothing in particular — order does not matter):

```python
@pytest.mark.asyncio
async def test_load_session_reads_fresh_redis_not_stale_memory(monkeypatch):
    """A poll on any worker must see the latest persisted state, not a stale
    in-memory copy cached by an earlier load."""
    svc = gc.GroupChatService()

    # Seed an old object in the in-memory map (simulating an earlier load).
    stale = _make_session("s9", current_round=0, max_rounds=5)
    svc._active_sessions["s9"] = stale

    # Redis holds newer state (round advanced by the Celery worker).
    fresh_data = {
        "session_id": "s9", "user_id": 1, "agent_ids": [1, 2],
        "messages": [{"role": "user", "content": "hi", "agent_id": None,
                      "agent_name": None, "timestamp": "t"}],
        "max_rounds": 5, "current_round": 3, "status": "active",
        "created_at": "t",
    }
    captured = {}

    async def fake_get_json(key):
        captured["key"] = key
        return fresh_data

    monkeypatch.setattr(gc.cache, "get_json", fake_get_json)

    loaded = await svc.load_session("s9")
    assert loaded is not None
    assert loaded.current_round == 3  # fresh Redis state, not the stale 0
    assert captured["key"] == "groupchat:session:s9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_group_chat_multiworker.py::test_load_session_reads_fresh_redis_not_stale_memory -v`
Expected: FAIL — current `load_session` returns the stale in-memory object (`current_round == 0`), so the assertion `== 3` fails.

- [ ] **Step 3: Make `load_session` read Redis first**

In `app/services/group_chat.py`, replace the body of `load_session` (the part that prefers the in-memory copy). Replace:
```python
        # Prefer the live in-memory session — within a single worker it holds the
        # freshest in-flight state (persist always writes memory -> Redis, never
        # the reverse during an active run). Rebuilding from Redis here would
        # reset an actively-running session AND swap the object out from under
        # run_to_completion, desyncing its loop counter. See group-chat hang.
        existing = self._active_sessions.get(session_id)
        if existing is not None:
            return existing

        data = await cache.get_json(f"groupchat:session:{session_id}")
```
with:
```python
        # Redis is authoritative. Completion now runs in a Celery worker (a
        # different process from the API workers serving polls), so the original
        # in-process object-swap hazard cannot occur here: no run_to_completion
        # loop shares this process with these polls. Always read fresh state.
        data = await cache.get_json(f"groupchat:session:{session_id}")
```
Leave the rest of `load_session` unchanged (it builds a `GroupChatSession` from `data`, stores it in `self._active_sessions[session_id]`, and returns it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_group_chat_multiworker.py -v`
Expected: PASS (4 tests).

Run the existing regression suite to confirm no break:
Run: `python -m pytest tests/test_group_chat_completion.py -v`
Expected: PASS (those tests drive `run_to_completion` via `_active_sessions` directly and do not call `load_session`, so they are unaffected).

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_multiworker.py
git commit -m "refactor(group_chat): load_session reads Redis authoritatively (multi-worker safe)"
```

---

## Task 3: Celery completion task + lock-guarded `start_completion`; remove in-process task machinery

**Files:**
- Modify: `app/workers/tasks.py` (add task + async helper)
- Modify: `app/services/group_chat.py` (`start_completion`, delete `_completion_tasks`/`_run_completion_safe`)
- Test: `tests/test_group_chat_multiworker.py` (add a dispatch test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_group_chat_multiworker.py`:

```python
@pytest.mark.asyncio
async def test_start_completion_dispatches_celery_once_under_lock(fake_redis, monkeypatch):
    svc = gc.GroupChatService()
    sess = _make_session("s5", current_round=0, max_rounds=3)

    async def fake_load(session_id):
        svc._active_sessions[session_id] = sess
        return sess

    monkeypatch.setattr(svc, "load_session", fake_load)

    dispatched = []

    class FakeTask:
        @staticmethod
        def apply_async(args=None, **kwargs):
            dispatched.append(args)

    import app.workers.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "run_group_chat_completion_task", FakeTask, raising=False)

    await svc.start_completion("s5")
    await svc.start_completion("s5")  # lock already held -> no second dispatch

    assert dispatched == [["s5"]]
    assert await svc.is_running("s5") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_group_chat_multiworker.py::test_start_completion_dispatches_celery_once_under_lock -v`
Expected: FAIL — the un-refactored `start_completion` does not dispatch Celery (it uses the old `asyncio.create_task`/`_completion_tasks` path and reads `_active_sessions` directly), so the test errors/fails before `dispatched` is ever populated (`dispatched == [["s5"]]` is not satisfied).

- [ ] **Step 3a: Add the Celery task to `app/workers/tasks.py`**

Append to `app/workers/tasks.py` (after the existing master-agent task block):
```python
async def _run_group_chat_completion_async(session_id: str) -> None:
    """Load the session from Redis, run it to completion, then release the lock.

    Runs inside the Celery worker (a separate process from the API), so the
    completion loop never shares an event loop with the request handlers.
    """
    from app.services.group_chat import GroupChatService
    service = GroupChatService()
    try:
        session = await service.load_session(session_id)
        if session is None:
            logger.warning(f"[group_chat_completion] session {session_id} not found")
            return
        await service.run_to_completion(session_id)
    finally:
        await service.release_run_lock(session_id)
        await service._clear_cancel_flag(session_id)


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def run_group_chat_completion_task(self, session_id: str):
    """Run a group-chat discussion to completion in the background."""
    logger.info(f"[run_group_chat_completion_task] session_id={session_id} started")
    try:
        asyncio.run(_run_group_chat_completion_async(session_id))
        logger.info(f"[run_group_chat_completion_task] session_id={session_id} completed")
        return {"status": "completed", "session_id": session_id}
    except Exception as e:
        logger.error(f"[run_group_chat_completion_task] session_id={session_id} error: {e}")
        raise
```

Verify `asyncio` and `logger` are already imported at the top of `app/workers/tasks.py` (they are — used by existing tasks). If `asyncio` is not imported, add `import asyncio` near the top.

- [ ] **Step 3b: Refactor `start_completion` and delete in-process machinery in `app/services/group_chat.py`**

Replace the `start_completion`, `_run_completion_safe`, and the `_completion_tasks` field. First, in `__init__`, delete these lines:
```python
        # Background completion runs, keyed by session_id. A session is
        # considered "running" iff it has an entry here. Running the whole
        # discussion inside the HTTP request blocks the single uvicorn worker;
        # start_completion() dispatches it here instead and returns immediately.
        self._completion_tasks: Dict[str, asyncio.Task] = {}
```

Replace the entire `start_completion` method:
```python
    async def start_completion(self, session_id: str) -> Dict[str, Any]:
        """Dispatch run_to_completion as a background task and return immediately.

        Idempotent: if a run is already in flight for this session, this is a
        no-op (it also structurally prevents the concurrent double-run that
        previously desynced run_to_completion's loop and pinned the event loop).
        """
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session_id not in self._completion_tasks:
            self._completion_tasks[session_id] = asyncio.create_task(
                self._run_completion_safe(session_id)
            )

        return await self.get_session_summary(session_id)
```
with:
```python
    async def start_completion(self, session_id: str) -> Dict[str, Any]:
        """Acquire the cross-worker run lock and dispatch the completion to Celery.

        Idempotent: if the lock is already held (a run is in flight on any
        worker), this is a no-op and just returns the current summary.
        """
        session = await self.load_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if await self.acquire_run_lock(session_id):
            await self._clear_cancel_flag(session_id)
            from app.workers.tasks import run_group_chat_completion_task
            run_group_chat_completion_task.apply_async(args=[session_id])

        return await self.get_session_summary(session_id)
```

Then delete the entire `_run_completion_safe` method (the whole `async def _run_completion_safe(self, session_id: str) -> None:` block, lines ~74-96 in the original).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_group_chat_multiworker.py -v`
Expected: PASS (5 tests).

Run: `python -c "import app.workers.tasks; import app.services.group_chat; print('ok')"`
Expected: `ok` (modules import cleanly; no dangling reference to `_completion_tasks` / `_run_completion_safe`).

Note: `tests/test_group_chat_completion.py` references `_run_completion_safe`? Verify:
Run: `grep -n "_run_completion_safe\|_completion_tasks" tests/test_group_chat_completion.py`
Expected: no matches. (Those tests drive `run_to_completion` directly.) If there ARE matches, those specific tests are now obsolete — update them to call `run_to_completion` directly instead, preserving their termination assertions.

- [ ] **Step 5: Commit**

```bash
git add app/workers/tasks.py app/services/group_chat.py tests/test_group_chat_multiworker.py
git commit -m "feat(group_chat): run completion as Celery task under a Redis lock"
```

---

## Task 4: Cross-worker cancel via the cancel flag; rewrite `cancel_session`

**Files:**
- Modify: `app/services/group_chat.py` (`run_to_completion` loop, `cancel_session`)
- Test: `tests/test_group_chat_multiworker.py` (add a cancel test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_group_chat_multiworker.py`:

```python
@pytest.mark.asyncio
async def test_run_to_completion_honors_cross_worker_cancel_flag(fake_redis, monkeypatch):
    """A cancel flag set by another worker stops the loop before the next round."""
    svc = gc.GroupChatService()
    sess = _make_session("s7", current_round=0, max_rounds=5)
    svc._active_sessions["s7"] = sess

    rounds_run = {"n": 0}

    async def fake_run_round(session_id):
        rounds_run["n"] += 1
        return {"session_id": session_id, "round": rounds_run["n"], "responses": []}

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "run_round", fake_run_round)
    monkeypatch.setattr(svc, "_generate_summary", _noop)
    monkeypatch.setattr(svc, "_persist_session", _noop)

    # Cancel was requested (by an API worker) before the run started.
    await svc._set_cancel_flag("s7")

    result = await svc.run_to_completion("s7")
    assert rounds_run["n"] == 0          # cancelled before any round ran
    assert result["session_id"] == "s7"


@pytest.mark.asyncio
async def test_cancel_session_sets_flag_and_status(fake_redis, monkeypatch):
    svc = gc.GroupChatService()
    sess = _make_session("s8", current_round=0, max_rounds=5)

    async def fake_load(session_id):
        return sess

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(svc, "load_session", fake_load)
    monkeypatch.setattr(svc, "_persist_session", _noop)

    assert await svc.cancel_session("s8") is True
    assert sess.status == "cancelled"
    assert await svc._is_cancelled("s8") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_group_chat_multiworker.py::test_run_to_completion_honors_cross_worker_cancel_flag tests/test_group_chat_multiworker.py::test_cancel_session_sets_flag_and_status -v`
Expected: FAIL — `run_to_completion` does not check the cancel flag (runs a round), and `cancel_session` still references `self._completion_tasks` (AttributeError after Task 3 deleted it) and does not set the flag.

- [ ] **Step 3a: Make `run_to_completion` poll the cancel flag**

In `app/services/group_chat.py`, in `run_to_completion`, inside the `while True:` loop, add the cancel check right after the existing `if session.current_round >= session.max_rounds: break`. The loop top currently reads:
```python
        while True:
            session = self._active_sessions.get(session_id)
            if not session or session.status != "active":
                break
            if session.current_round >= session.max_rounds:
                break

            round_result = await self.run_round(session_id)
```
Change it to:
```python
        while True:
            session = self._active_sessions.get(session_id)
            if not session or session.status != "active":
                break
            if await self._is_cancelled(session_id):
                session.status = "cancelled"
                break
            if session.current_round >= session.max_rounds:
                break

            round_result = await self.run_round(session_id)
```

- [ ] **Step 3b: Rewrite `cancel_session`**

Replace the entire `cancel_session` method:
```python
    async def cancel_session(self, session_id: str) -> bool:
        """
        Cancel an active session.
        
        Args:
            session_id: Session to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        session = self._active_sessions.get(session_id)
        if not session:
            return False

        session.status = "cancelled"
        await self._persist_session(session)

        # Stop any in-flight background completion run promptly. (run_to_completion
        # also checks status == "active" each iteration, but cancelling the task
        # avoids waiting for the current round to finish.)
        task = self._completion_tasks.get(session_id)
        if task is not None:
            task.cancel()

        return True
```
with:
```python
    async def cancel_session(self, session_id: str) -> bool:
        """Cancel an active session (cross-worker).

        Sets status=cancelled in Redis and raises a dedicated cancel flag that
        the Celery completion loop polls each round. The flag is a separate key
        the running task never overwrites, so a cancel cannot be clobbered by
        the task's own end-of-round persist.

        Returns True if cancelled, False if not found.
        """
        session = await self.load_session(session_id)
        if not session:
            return False

        session.status = "cancelled"
        await self._persist_session(session)
        await self._set_cancel_flag(session_id)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_group_chat_multiworker.py tests/test_group_chat_completion.py -v`
Expected: PASS (all multiworker tests + the existing completion regression tests).

**If the existing `test_group_chat_completion.py` tests slow down or hang:** the
new per-iteration `await self._is_cancelled(session_id)` calls `get_redis()`,
which (with no fake Redis configured in those tests) attempts a real connection
each loop iteration. `_is_cancelled` catches the failure and returns `False`, so
behavior is correct, but the connection attempts add latency. If observed, make
those tests immune by patching `get_redis` to fail fast — add to each test that
drives `run_to_completion`:
```python
    async def _no_redis():
        raise ConnectionError("no redis in unit test")
    monkeypatch.setattr("app.services.group_chat.get_redis", _no_redis)
```
(They already take a `monkeypatch` fixture.) This keeps `_is_cancelled` returning
`False` instantly, preserving the original loop behavior the tests assert.

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_multiworker.py
git commit -m "feat(group_chat): cross-worker cancel via Redis flag; Celery-safe cancel_session"
```

---

## Task 5: `await` the now-async `is_running` in the router

**Files:**
- Modify: `app/routers/groupchat.py`

- [ ] **Step 1: Find the call sites**

Run: `grep -n "is_running" app/routers/groupchat.py`
Expected: two hits, both `running=service.is_running(session_id),` (in the `/complete` and status responses, around lines 103 and 204).

- [ ] **Step 2: Add `await` to both**

In `app/routers/groupchat.py`, change each occurrence of:
```python
        running=service.is_running(session_id),
```
to:
```python
        running=await service.is_running(session_id),
```
Both call sites are inside `async def` route handlers, so `await` is valid. Use `grep` to confirm none are missed:
Run: `grep -n "service.is_running" app/routers/groupchat.py`
Expected after edit: every hit is preceded by `await`.

- [ ] **Step 3: Verify the router imports/parses cleanly**

Run: `python -c "import ast; ast.parse(open('app/routers/groupchat.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/routers/groupchat.py
git commit -m "fix(groupchat-router): await now-async is_running"
```

---

## Final verification

- [ ] Full Phase 2 + regression suite:

Run: `python -m pytest tests/test_group_chat_multiworker.py tests/test_group_chat_completion.py -v`
Expected: all PASS.

- [ ] No in-process completion machinery remains:

Run: `grep -rn "_completion_tasks\|_run_completion_safe\|asyncio.create_task" app/services/group_chat.py`
Expected: no matches.

- [ ] No unawaited `is_running` remains:

Run: `grep -rn "service.is_running\|self.is_running" app --include="*.py" | grep -v "await "`
Expected: no matches.

- [ ] Modules import cleanly together:

Run: `python -c "import app.services.group_chat, app.workers.tasks, app.routers.groupchat; print('ok')"`
Expected: `ok`

## Risks

- **DB access inside the Celery completion run.** `_generate_summary` opens an
  `AsyncSessionLocal` under `asyncio.run` in the Celery worker. The master-agent
  task already runs AgentExecutor + DB this way, so the path is proven; and
  `_generate_summary` is best-effort (its own try/except logs and continues), so a
  cross-loop hiccup degrades to "no summary," not a crash. Covered by a manual
  integration smoke (start a real `/complete`, confirm rounds + summary persist).
- **Lock TTL vs run length.** `_RUN_LOCK_TTL = 3600s`. A run exceeding this would
  drop its lock and allow a duplicate dispatch. Group-chat runs are bounded by
  `max_rounds` (default 5) of LLM calls — far under an hour. If longer runs become
  possible, add periodic lock refresh; out of scope now.
