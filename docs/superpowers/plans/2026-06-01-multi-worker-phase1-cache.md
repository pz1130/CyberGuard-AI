# Multi-Worker Phase 1 — Versioned Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `master_config` and `security_settings` in-process caches cross-worker-correct by gating them on a Redis version counter, so an update on any worker is observed by all workers.

**Architecture:** A reusable `VersionedCache` helper holds a process-local `(version, value)` pair. On read it does a cheap `GET cache:ver:<ns>`; if the Redis version differs from the local one, it reloads via a caller-supplied loader. Writes `INCR` the version (and adopt the new value locally). If Redis is unreachable, the cache degrades to loading on every read (correct, just uncached). The two services are refactored to use this helper instead of bare module globals.

**Tech Stack:** Python 3.11, `redis.asyncio` (via existing `app/core/redis_client.get_redis`), `unittest` + `unittest.IsolatedAsyncioTestCase`.

**Scope note:** This is Phase 1 of the multi-worker unblock (spec: `docs/superpowers/specs/2026-06-01-multi-worker-unblock-design.md`). It is shippable on its own and safe under single-worker. Phases 2 (group chat) and 3 (MCP) get their own plans. The multi-worker flip happens in Phase 4, not here.

**Run tests with:** `python -m unittest tests.test_versioned_cache -v` (no external services — Redis is faked).

---

## File Structure

- `app/core/versioned_cache.py` — **new.** The `VersionedCache` helper. Single responsibility: version-gated process-local caching over Redis.
- `app/services/master_config.py` — **modify.** Replace the `_config_cache` global with a module-level `VersionedCache`; `get`/`update`/`invalidate` delegate to it.
- `app/services/security_settings.py` — **modify.** Same refactor with its own namespace.
- `app/routers/master_config.py` — **modify.** The one caller of `invalidate_cache()` must `await` it (now async).
- `tests/test_versioned_cache.py` — **new.** Full unit coverage of the helper with a fake Redis.
- `tests/test_config_cache_wiring.py` — **new.** Verifies each service delegates to its cache (load-through, bump-on-update) using a spy cache; no DB needed.

---

## Task 1: `VersionedCache` helper

**Files:**
- Create: `app/core/versioned_cache.py`
- Test: `tests/test_versioned_cache.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_versioned_cache.py`:

```python
import unittest
from app.core.versioned_cache import VersionedCache


class FakeRedis:
    """Mimics redis.asyncio with decode_responses=True: get -> str|None, incr -> int."""
    def __init__(self):
        self.store: dict[str, str] = {}
        self.get_calls = 0

    async def get(self, key):
        self.get_calls += 1
        return self.store.get(key)

    async def incr(self, key):
        v = int(self.store.get(key, "0")) + 1
        self.store[key] = str(v)
        return v


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("redis down")

    async def incr(self, key):
        raise ConnectionError("redis down")


def _getter(client):
    async def _get():
        return client
    return _get


class TestVersionedCache(unittest.IsolatedAsyncioTestCase):
    async def test_loads_once_then_serves_from_local(self):
        r = FakeRedis()
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return f"value-{calls['n']}"

        c = VersionedCache("master_config", redis_getter=_getter(r))
        self.assertEqual(await c.get(loader), "value-1")
        self.assertEqual(await c.get(loader), "value-1")  # cached, loader not re-called
        self.assertEqual(calls["n"], 1)

    async def test_bump_on_one_instance_invalidates_another(self):
        r = FakeRedis()  # shared "redis" across two cache instances
        a_calls = {"n": 0}
        b_calls = {"n": 0}

        async def a_loader():
            a_calls["n"] += 1
            return f"a-{a_calls['n']}"

        async def b_loader():
            b_calls["n"] += 1
            return f"b-{b_calls['n']}"

        a = VersionedCache("ns", redis_getter=_getter(r))
        b = VersionedCache("ns", redis_getter=_getter(r))
        await a.get(a_loader)            # a caches at version 0
        await b.get(b_loader)            # b caches at version 0
        await a.bump()                   # global version -> 1
        await b.get(b_loader)            # b sees new version -> reloads
        self.assertEqual(b_calls["n"], 2)

    async def test_bump_with_value_adopts_locally_without_reload(self):
        r = FakeRedis()
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return "loaded"

        c = VersionedCache("ns", redis_getter=_getter(r))
        await c.get(loader)              # version 0, 1 load
        await c.bump("written")          # writer adopts new value under new version
        self.assertEqual(await c.get(loader), "written")  # no reload
        self.assertEqual(calls["n"], 1)

    async def test_redis_down_degrades_to_reload_every_read(self):
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return "v"

        c = VersionedCache("ns", redis_getter=_getter(BrokenRedis()))
        await c.get(loader)
        await c.get(loader)
        self.assertEqual(calls["n"], 2)  # never cached because version unknown


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_versioned_cache -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.versioned_cache'`

- [ ] **Step 3: Implement `VersionedCache`**

Create `app/core/versioned_cache.py`:

```python
"""Version-gated process-local cache.

Each cache namespace has a Redis integer version key (`cache:ver:<ns>`). On
read we do a cheap GET of that key; if it differs from the locally-stored
version, we reload via the caller's loader and adopt the new version. Writes
INCR the version (and may adopt the new value locally so the writer does not
reload on its next read). If Redis is unreachable, the cache degrades to
loading on every read — correct, just uncached.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Generic, Optional, TypeVar

from app.core.redis_client import get_redis

T = TypeVar("T")


class VersionedCache(Generic[T]):
    def __init__(
        self,
        namespace: str,
        *,
        redis_getter: Callable[[], Awaitable] = get_redis,
    ) -> None:
        self._ver_key = f"cache:ver:{namespace}"
        self._redis_getter = redis_getter
        self._local_version: Optional[str] = None
        self._local_value: Optional[T] = None

    async def get(self, loader: Callable[[], Awaitable[T]]) -> T:
        """Return the cached value, reloading via `loader` when the global
        version has advanced (or Redis is unavailable)."""
        try:
            client = await self._redis_getter()
            version = await client.get(self._ver_key)
        except Exception:
            # Redis unavailable: cannot trust local freshness -> reload, do not cache.
            value = await loader()
            self._local_value = value
            self._local_version = None
            return value

        version = version if version is not None else "0"
        if version == self._local_version and self._local_value is not None:
            return self._local_value

        value = await loader()
        self._local_value = value
        self._local_version = version
        return value

    async def bump(self, new_value: Optional[T] = None) -> None:
        """Advance the global version. If `new_value` is given, adopt it locally
        under the new version (so the writer does not reload next read);
        otherwise force the next read to reload."""
        try:
            client = await self._redis_getter()
            new_version = await client.incr(self._ver_key)
            if new_value is not None:
                self._local_value = new_value
                self._local_version = str(new_version)
            else:
                self._local_version = None
        except Exception:
            # Redis down: best-effort local update; peers cannot be notified.
            if new_value is not None:
                self._local_value = new_value
            self._local_version = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_versioned_cache -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/versioned_cache.py tests/test_versioned_cache.py
git commit -m "feat(cache): add VersionedCache (Redis version-gated process-local cache)"
```
(a git hook may auto-push; expected.)

---

## Task 2: Refactor `master_config` to use `VersionedCache`

**Files:**
- Modify: `app/services/master_config.py`
- Test: `tests/test_config_cache_wiring.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_cache_wiring.py`:

```python
import unittest
from unittest.mock import AsyncMock, patch


class TestMasterConfigCacheWiring(unittest.IsolatedAsyncioTestCase):
    async def test_get_delegates_to_versioned_cache(self):
        import app.services.master_config as mc
        sentinel = object()
        fake_cache = AsyncMock()
        fake_cache.get.return_value = sentinel
        with patch.object(mc, "_cache", fake_cache):
            result = await mc.get_master_config(db=AsyncMock())
        self.assertIs(result, sentinel)
        self.assertEqual(fake_cache.get.await_count, 1)

    async def test_update_bumps_cache_with_new_config(self):
        import app.services.master_config as mc
        db = AsyncMock()
        updated = object()
        db.get.return_value = object()  # existing row
        db.refresh = AsyncMock()
        fake_cache = AsyncMock()
        with patch.object(mc, "_cache", fake_cache), \
             patch.object(mc, "_apply_and_refresh", AsyncMock(return_value=updated)):
            await mc.update_master_config(db, {"temperature": 0.5})
        fake_cache.bump.assert_awaited_once_with(updated)

    async def test_invalidate_is_async_and_bumps(self):
        import app.services.master_config as mc
        fake_cache = AsyncMock()
        with patch.object(mc, "_cache", fake_cache):
            await mc.invalidate_cache()
        fake_cache.bump.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_config_cache_wiring.TestMasterConfigCacheWiring -v`
Expected: FAIL — `AttributeError: module 'app.services.master_config' has no attribute '_cache'` (and no `_apply_and_refresh`).

- [ ] **Step 3: Refactor `master_config.py`**

Replace the entire contents of `app/services/master_config.py` with:

```python
"""Master Agent configuration service (version-cached for multi-worker)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.master_config import MasterAgentConfig
from app.core.versioned_cache import VersionedCache

# Cross-worker version-gated cache (replaces the old process-local global).
_cache: VersionedCache[MasterAgentConfig] = VersionedCache("master_config")


async def _load_or_create(db: AsyncSession) -> MasterAgentConfig:
    """Load the single config row, creating the default if absent."""
    result = await db.execute(select(MasterAgentConfig).where(MasterAgentConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        default_intent = """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, group_chat, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Agent types: threat_intel, log_anomaly, vuln_scanner, remediation, compliance, osint, general
"""
        default_summary = "You are CyberGuard's summarizer. Create a concise summary of agent results for the user."
        default_system = "You are CyberGuard, a security operations assistant. You help users with threat analysis, vulnerability assessment, log analysis, and security compliance. Be precise and actionable."
        config = MasterAgentConfig(
            id=1,
            model="MiniMax-m2.7",
            temperature=0.7,
            system_prompt=default_system,
            intent_parser_prompt=default_intent,
            summarizer_prompt=default_summary,
            max_rounds=10,
            auto_approve_threshold=0,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


async def _apply_and_refresh(db: AsyncSession, data: dict) -> MasterAgentConfig:
    """Apply `data` to the existing row, commit, and return the refreshed object."""
    config = await db.get(MasterAgentConfig, 1)
    if not config:
        return await _load_or_create(db)
    for key, value in data.items():
        if hasattr(config, key) and value is not None:
            setattr(config, key, value)
    await db.commit()
    await db.refresh(config)
    return config


async def get_master_config(db: AsyncSession) -> MasterAgentConfig:
    """Get master agent config, creating default if not exists (version-cached)."""
    return await _cache.get(lambda: _load_or_create(db))


async def update_master_config(db: AsyncSession, data: dict) -> MasterAgentConfig:
    """Update master agent config and bump the cross-worker cache version."""
    config = await _apply_and_refresh(db, data)
    await _cache.bump(config)
    return config


async def invalidate_cache() -> None:
    """Invalidate the cache across all workers (bumps the global version)."""
    await _cache.bump()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_config_cache_wiring.TestMasterConfigCacheWiring -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/master_config.py tests/test_config_cache_wiring.py
git commit -m "refactor(master_config): use VersionedCache for cross-worker invalidation"
```

---

## Task 3: Refactor `security_settings` to use `VersionedCache`

**Files:**
- Modify: `app/services/security_settings.py`
- Test: `tests/test_config_cache_wiring.py` (append a second test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config_cache_wiring.py` (before the `if __name__` block):

```python
class TestSecuritySettingsCacheWiring(unittest.IsolatedAsyncioTestCase):
    async def test_get_delegates_to_versioned_cache(self):
        import app.services.security_settings as ss
        sentinel = object()
        fake_cache = AsyncMock()
        fake_cache.get.return_value = sentinel
        with patch.object(ss, "_cache", fake_cache):
            result = await ss.get_security_settings(db=AsyncMock())
        self.assertIs(result, sentinel)
        self.assertEqual(fake_cache.get.await_count, 1)

    async def test_update_bumps_cache_with_new_settings(self):
        import app.services.security_settings as ss
        db = AsyncMock()
        updated = object()
        with patch.object(ss, "_cache", AsyncMock()) as fake_cache, \
             patch.object(ss, "_apply_and_refresh", AsyncMock(return_value=updated)):
            await ss.update_security_settings(db, {"max_login_attempts": 3})
        fake_cache.bump.assert_awaited_once_with(updated)

    async def test_invalidate_is_async_and_bumps(self):
        import app.services.security_settings as ss
        fake_cache = AsyncMock()
        with patch.object(ss, "_cache", fake_cache):
            await ss.invalidate_cache()
        fake_cache.bump.assert_awaited_once_with()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_config_cache_wiring.TestSecuritySettingsCacheWiring -v`
Expected: FAIL — `AttributeError: module 'app.services.security_settings' has no attribute '_cache'`.

- [ ] **Step 3: Refactor `security_settings.py`**

Replace the entire contents of `app/services/security_settings.py` with:

```python
"""Security settings service (single-row, version-cached for multi-worker)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.security_settings import SecuritySettings
from app.core.versioned_cache import VersionedCache

_cache: VersionedCache[SecuritySettings] = VersionedCache("security_settings")


async def _load_or_create(db: AsyncSession) -> SecuritySettings:
    result = await db.execute(select(SecuritySettings).where(SecuritySettings.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = SecuritySettings(
            id=1,
            encryption_enabled=True,
            rbac_enabled=True,
            audit_logging=True,
            max_login_attempts=5,
            session_timeout_minutes=30,
            api_key_rotation_days=90,
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def _apply_and_refresh(db: AsyncSession, data: dict) -> SecuritySettings:
    cfg = await db.get(SecuritySettings, 1)
    if not cfg:
        return await _load_or_create(db)
    for key, value in data.items():
        if hasattr(cfg, key) and value is not None:
            setattr(cfg, key, value)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def get_security_settings(db: AsyncSession) -> SecuritySettings:
    return await _cache.get(lambda: _load_or_create(db))


async def update_security_settings(db: AsyncSession, data: dict) -> SecuritySettings:
    cfg = await _apply_and_refresh(db, data)
    await _cache.bump(cfg)
    return cfg


async def invalidate_cache() -> None:
    await _cache.bump()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_config_cache_wiring -v`
Expected: PASS (both test classes, 6 tests total)

- [ ] **Step 5: Commit**

```bash
git add app/services/security_settings.py tests/test_config_cache_wiring.py
git commit -m "refactor(security_settings): use VersionedCache for cross-worker invalidation"
```

---

## Task 4: Update the `invalidate_cache()` caller (now async)

**Files:**
- Modify: `app/routers/master_config.py` (the `invalidate_cache()` call near line 55-58)

- [ ] **Step 1: Locate the caller and confirm the route is async**

Run: `grep -n "invalidate_cache\|async def\|def " app/routers/master_config.py | head -30`
Expected: shows an `import ... invalidate_cache` and a bare `invalidate_cache()` call inside an `async def` route handler.

- [ ] **Step 2: Make the call `await`**

In `app/routers/master_config.py`, change the call:
```python
    invalidate_cache()
```
to:
```python
    await invalidate_cache()
```
Leave the surrounding update logic unchanged. (The update path already bumps the version via `update_master_config`; this explicit call is now redundant-but-harmless and simply bumps again — keep it to avoid changing the route's behavior contract.)

Then grep the whole app for any other caller that must be awaited:
Run: `grep -rn "invalidate_cache()" app --include="*.py" | grep -v "async def invalidate_cache"`
For each hit that is NOT preceded by `await`, add `await`. (Both `master_config` and `security_settings` now expose an async `invalidate_cache`.)

- [ ] **Step 3: Verify the modules import cleanly**

Run: `python -c "import ast; ast.parse(open('app/routers/master_config.py').read()); print('ok')"`
Expected: `ok`

Run: `python -m unittest tests.test_versioned_cache tests.test_config_cache_wiring -v`
Expected: all PASS (no regression).

- [ ] **Step 4: Commit**

```bash
git add app/routers/master_config.py
git commit -m "fix(routers): await now-async invalidate_cache()"
```

---

## Final verification

- [ ] Run the full Phase 1 suite:

Run: `python -m unittest tests.test_versioned_cache tests.test_config_cache_wiring -v`
Expected: all PASS (10 tests).

- [ ] Confirm no bare `invalidate_cache()` call remains unawaited:

Run: `grep -rn "invalidate_cache()" app --include="*.py" | grep -v "await invalidate_cache" | grep -v "async def invalidate_cache"`
Expected: no matches (exit 1).

- [ ] Confirm the old process-local globals are gone:

Run: `grep -rn "_config_cache\|^_cache = None\|_cache: Optional" app/services/master_config.py app/services/security_settings.py`
Expected: no matches (the only `_cache` is now the `VersionedCache` instance).
