"""Brute-force protection: max_login_attempts stops being decorative.

The Security page has offered `max_login_attempts` since migration 013 and
nothing read it, so a security-operations product shipped with no limit at all
on password guessing. This enforces it.

Shape follows tests/test_idle_session_timeout.py: Redis holds the state, the
setting is read at request time so an operator's change takes effect on the
next attempt rather than the next restart, and Redis being unavailable fails
*open* — matching is_token_revoked and session_is_idle, because failing closed
would lock every operator out of an incident-response tool on a Redis blip.
"""
from __future__ import annotations

import pytest

from app.core import login_guard


class _FakeRedis:
    def __init__(self):
        self.keys: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key):
        value = int(self.keys.get(key, 0)) + 1
        self.keys[key] = str(value)
        return value

    async def expire(self, key, ttl):
        if key not in self.keys:
            return False
        self.ttls[key] = ttl
        return True

    async def set(self, key, value, ex=None):
        self.keys[key] = str(value)
        self.ttls[key] = ex

    async def exists(self, key):
        return 1 if key in self.keys else 0

    async def delete(self, *keys):
        for key in keys:
            self.keys.pop(key, None)
            self.ttls.pop(key, None)


@pytest.fixture
def redis(monkeypatch):
    fake = _FakeRedis()

    async def get_redis():
        return fake

    monkeypatch.setattr("app.core.redis_client.get_redis", get_redis)
    return fake


# --- counting ---

@pytest.mark.asyncio
async def test_a_failure_is_counted(redis):
    assert await login_guard.record_failure("amy", max_attempts=3) == 1
    assert await login_guard.record_failure("amy", max_attempts=3) == 2


@pytest.mark.asyncio
async def test_reaching_the_limit_locks_the_account(redis):
    for _ in range(3):
        await login_guard.record_failure("amy", max_attempts=3)
    assert await login_guard.is_locked("amy") is True


@pytest.mark.asyncio
async def test_staying_below_the_limit_does_not_lock(redis):
    for _ in range(2):
        await login_guard.record_failure("amy", max_attempts=3)
    assert await login_guard.is_locked("amy") is False


@pytest.mark.asyncio
async def test_the_lock_carries_the_agreed_fifteen_minute_window(redis):
    for _ in range(3):
        await login_guard.record_failure("amy", max_attempts=3)
    assert redis.ttls[login_guard._lock_key("amy")] == 15 * 60
    assert login_guard.LOCKOUT_SECONDS == 15 * 60


@pytest.mark.asyncio
async def test_a_successful_login_clears_the_count(redis):
    await login_guard.record_failure("amy", max_attempts=3)
    await login_guard.record_failure("amy", max_attempts=3)
    await login_guard.clear("amy")
    assert await login_guard.record_failure("amy", max_attempts=3) == 1
    assert await login_guard.is_locked("amy") is False


@pytest.mark.asyncio
async def test_accounts_are_counted_separately(redis):
    await login_guard.record_failure("amy", max_attempts=2)
    await login_guard.record_failure("amy", max_attempts=2)
    assert await login_guard.is_locked("amy") is True
    assert await login_guard.is_locked("bob") is False


@pytest.mark.asyncio
async def test_usernames_are_normalised_so_case_cannot_reset_the_counter(redis):
    """Otherwise AMY, Amy and amy would each get their own budget."""
    await login_guard.record_failure("amy", max_attempts=2)
    await login_guard.record_failure("AMY", max_attempts=2)
    assert await login_guard.is_locked("Amy") is True


# --- the properties that make it safe to ship ---

@pytest.mark.asyncio
async def test_zero_disables_the_feature(redis):
    """0 has to mean "no limit"; treating it as "lock immediately" would make an
    empty settings row unusable. Matches session_timeout_minutes."""
    assert await login_guard.record_failure("amy", max_attempts=0) == 0
    assert await login_guard.is_locked("amy") is False


@pytest.mark.asyncio
async def test_redis_being_down_does_not_lock_anyone_out(monkeypatch):
    """Failing closed here would bar every operator from an incident-response
    tool the moment Redis hiccups. Matches is_token_revoked."""
    async def no_redis():
        return None

    monkeypatch.setattr("app.core.redis_client.get_redis", no_redis)
    assert await login_guard.is_locked("amy") is False
    assert await login_guard.record_failure("amy", max_attempts=3) == 0


@pytest.mark.asyncio
async def test_an_unknown_username_is_counted_like_any_other(redis):
    """If only real accounts were counted, whether a lockout happens would
    reveal which usernames exist."""
    await login_guard.record_failure("does-not-exist", max_attempts=1)
    assert await login_guard.is_locked("does-not-exist") is True


# --- wiring: the setting is read, and the endpoint uses it ---

@pytest.mark.asyncio
async def test_the_configured_value_is_what_gets_applied(monkeypatch):
    from app.routers import auth as auth_router

    attempts = {"value": 4}

    async def fake_settings(_db):
        class _Cfg:
            max_login_attempts = attempts["value"]
        return _Cfg()

    monkeypatch.setattr(
        "app.services.security_settings.get_security_settings", fake_settings)

    assert await auth_router._max_login_attempts(None) == 4
    attempts["value"] = 9
    assert await auth_router._max_login_attempts(None) == 9


def test_the_login_endpoint_consults_the_guard():
    """Asserted on the source so a refactor that drops the check shows up here
    rather than as a quiet hole in the login path."""
    import inspect

    from app.routers.auth import login

    src = inspect.getsource(login)
    assert "is_locked" in src, "login no longer checks for a locked account"
    assert "record_failure" in src, "login no longer counts a failed attempt"
    assert "clear" in src, "login no longer resets the counter on success"


def test_a_lockout_is_audited():
    """Brute force being stopped is itself a security event worth evidencing."""
    import inspect

    from app.routers.auth import login

    src = inspect.getsource(login)
    assert "auth.account_locked" in src
