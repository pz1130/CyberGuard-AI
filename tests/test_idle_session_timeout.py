"""Idle logout enforced on the server, not just in the browser.

`session_timeout_minutes` has been configurable on the Security page since
migration 013 and nothing read it. Clearing localStorage on a timer would not
change that: the token stays valid for ACCESS_TOKEN_EXPIRE_MINUTES (24h), so
anyone holding it still has a session.

The refresh happens only on an explicit heartbeat. That is what makes the
feature work at all — the UI polls every 30 seconds on every page, so if any
request counted as activity the timer would never run out.
"""
from __future__ import annotations

import pytest

from app.core import auth as auth_mod


class _FakeRedis:
    def __init__(self):
        self.keys: dict[str, int] = {}

    async def set(self, key, _value, ex=None):
        self.keys[key] = ex

    async def expire(self, key, ttl):
        if key not in self.keys:
            return False
        self.keys[key] = ttl
        return True

    async def exists(self, key):
        return 1 if key in self.keys else 0

    async def delete(self, key):
        self.keys.pop(key, None)


@pytest.fixture
def redis(monkeypatch):
    fake = _FakeRedis()

    async def get_redis():
        return fake

    monkeypatch.setattr("app.core.redis_client.get_redis", get_redis)
    return fake


# --- the key itself ---

@pytest.mark.asyncio
async def test_starting_a_session_records_it_with_the_configured_ttl(redis):
    await auth_mod.start_session("jti-1", idle_minutes=30)
    assert redis.keys["session:active:jti-1"] == 30 * 60


@pytest.mark.asyncio
async def test_a_live_session_is_not_idle(redis):
    await auth_mod.start_session("jti-1", idle_minutes=30)
    assert await auth_mod.session_is_idle("jti-1") is False


@pytest.mark.asyncio
async def test_a_session_whose_key_expired_is_idle(redis):
    await auth_mod.start_session("jti-1", idle_minutes=30)
    redis.keys.pop("session:active:jti-1")  # what Redis does when the TTL runs out
    assert await auth_mod.session_is_idle("jti-1") is True


@pytest.mark.asyncio
async def test_a_heartbeat_extends_a_live_session(redis):
    await auth_mod.start_session("jti-1", idle_minutes=30)
    assert await auth_mod.touch_session("jti-1", idle_minutes=45) is True
    assert redis.keys["session:active:jti-1"] == 45 * 60


@pytest.mark.asyncio
async def test_a_heartbeat_does_not_resurrect_an_expired_session(redis):
    # Otherwise a tab left open overnight would quietly come back to life.
    assert await auth_mod.touch_session("jti-1", idle_minutes=30) is False
    assert "session:active:jti-1" not in redis.keys


@pytest.mark.asyncio
async def test_ending_a_session_removes_the_key(redis):
    await auth_mod.start_session("jti-1", idle_minutes=30)
    await auth_mod.end_session("jti-1")
    assert await auth_mod.session_is_idle("jti-1") is True


# --- the availability posture ---

@pytest.mark.asyncio
async def test_redis_being_down_does_not_log_everyone_out(monkeypatch):
    """Matches is_token_revoked, which returns False when Redis is unavailable.

    Failing closed here would drop every signed-in user on a Redis blip; failing
    open falls back to the 24h token expiry, which is today's behaviour.
    """
    async def no_redis():
        return None

    monkeypatch.setattr("app.core.redis_client.get_redis", no_redis)
    assert await auth_mod.session_is_idle("jti-1") is False


# --- the property the whole feature rests on ---

@pytest.mark.asyncio
async def test_verifying_a_token_does_not_extend_the_session(redis, monkeypatch):
    """Polling must not count as activity.

    HeaderNew polls every 30s on every page. If verify_token refreshed the TTL,
    a 30-minute idle timeout would never once fire.
    """
    token = auth_mod.create_access_token({"sub": "1", "username": "u", "role": "admin"})
    jti = auth_mod.jwt.decode(
        token, auth_mod.settings.SECRET_KEY, algorithms=[auth_mod.ALGORITHM])["jti"]

    await auth_mod.start_session(jti, idle_minutes=30)
    redis.keys["session:active:" + jti] = 5  # pretend 5s of TTL is left

    await auth_mod.verify_token(token)
    assert redis.keys["session:active:" + jti] == 5, (
        "verify_token extended the session, so background polling would keep it "
        "alive forever"
    )


@pytest.mark.asyncio
async def test_an_idle_session_rejects_its_token(redis):
    token = auth_mod.create_access_token({"sub": "1", "username": "u", "role": "admin"})
    jti = auth_mod.jwt.decode(
        token, auth_mod.settings.SECRET_KEY, algorithms=[auth_mod.ALGORITHM])["jti"]
    await auth_mod.start_session(jti, idle_minutes=30)

    assert await auth_mod.verify_token(token) is not None
    redis.keys.pop("session:active:" + jti)
    assert await auth_mod.verify_token(token) is None


@pytest.mark.asyncio
async def test_no_session_key_means_expired_not_grandfathered(redis):
    """Absence is expiry, with no exception for tokens issued before this shipped.

    The alternative — creating the key on first use when it is missing — would
    let a background poll resurrect a session that had already timed out, which
    is the one outcome this feature exists to prevent. The cost is that
    deploying it signs everyone out once, which is ordinary for a session change.
    """
    token = auth_mod.create_access_token({"sub": "1", "username": "u", "role": "admin"})
    assert await auth_mod.verify_token(token) is None

    payload_jti = auth_mod.jwt.decode(
        token, auth_mod.settings.SECRET_KEY,
        algorithms=[auth_mod.ALGORITHM])["jti"]
    assert "session:active:" + payload_jti not in redis.keys, (
        "verifying a token must never create the session key"
    )


# --- the setting is actually wired to the behaviour ---

@pytest.mark.asyncio
async def test_the_configured_value_is_what_gets_applied(redis, monkeypatch):
    """The point of the whole change: session_timeout_minutes stops being inert.

    Reading it at heartbeat time rather than caching it per-session means an
    operator lowering the window takes effect on the next beat, not on the next
    login.
    """
    from app.routers import auth as auth_router

    minutes = {"value": 15}

    async def fake_settings(_db):
        class _Cfg:
            session_timeout_minutes = minutes["value"]
        return _Cfg()

    monkeypatch.setattr(
        "app.services.security_settings.get_security_settings", fake_settings)

    assert await auth_router._idle_minutes(None) == 15

    await auth_mod.start_session("jti-1", idle_minutes=15)
    assert redis.keys["session:active:jti-1"] == 15 * 60

    minutes["value"] = 45  # an operator widens the window
    assert await auth_router._idle_minutes(None) == 45
    await auth_mod.touch_session("jti-1", idle_minutes=await auth_router._idle_minutes(None))
    assert redis.keys["session:active:jti-1"] == 45 * 60


@pytest.mark.asyncio
async def test_a_zero_timeout_disables_the_feature_rather_than_locking_everyone_out(redis):
    """0 has to mean "no idle limit"; treating it as "expire instantly" would
    make an empty settings row unusable."""
    await auth_mod.start_session("jti-1", idle_minutes=0)
    assert "session:active:jti-1" not in redis.keys
    assert await auth_mod.touch_session("jti-1", idle_minutes=0) is False
