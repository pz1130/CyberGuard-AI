"""A user changing their own password.

There was no way to do it. PasswordChangeRequest had been defined and exported
since early on and no endpoint ever consumed it, so the only route to a new
password was asking an admin to set one — which means the admin knows it, and
a user whose password leaks cannot act without them.

Two properties carry the security of this endpoint:

* **The old password is required.** Without that check a stolen token would be
  enough to seize the account permanently, turning temporary session theft into
  a takeover.
* **Other sessions end.** "I think my password leaked" is the reason people
  change passwords, and it is not answered by changing the secret while the
  attacker's session keeps working.
"""
from __future__ import annotations

import uuid

import pytest

from app.core import auth as auth_mod


class _FakeRedis:
    def __init__(self):
        self.keys: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    async def set(self, key, value, ex=None):
        self.keys[key] = str(value)

    async def exists(self, key):
        return 1 if key in self.keys else 0

    async def delete(self, *keys):
        for key in keys:
            self.keys.pop(key, None)
            self.sets.pop(key, None)

    async def expire(self, key, ttl):
        return key in self.keys

    async def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(str(m) for m in members)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def srem(self, key, *members):
        self.sets.get(key, set()).difference_update(str(m) for m in members)


@pytest.fixture
def redis(monkeypatch):
    fake = _FakeRedis()

    async def get_redis():
        return fake

    monkeypatch.setattr("app.core.redis_client.get_redis", get_redis)
    return fake


# --- ending other sessions ---

@pytest.mark.asyncio
async def test_a_session_is_indexed_against_its_user(redis):
    await auth_mod.start_session("jti-a", idle_minutes=30, user_id=7)
    assert "jti-a" in await redis.smembers(auth_mod._user_sessions_key(7))


@pytest.mark.asyncio
async def test_other_sessions_end_and_the_current_one_survives(redis):
    for jti in ("phone", "laptop", "attacker"):
        await auth_mod.start_session(jti, idle_minutes=30, user_id=7)

    ended = await auth_mod.end_other_sessions(user_id=7, keep_jti="laptop")

    assert ended == 2
    assert await auth_mod.session_is_idle("laptop") is False
    assert await auth_mod.session_is_idle("phone") is True
    assert await auth_mod.session_is_idle("attacker") is True


@pytest.mark.asyncio
async def test_another_users_sessions_are_untouched(redis):
    await auth_mod.start_session("mine", idle_minutes=30, user_id=7)
    await auth_mod.start_session("theirs", idle_minutes=30, user_id=8)

    await auth_mod.end_other_sessions(user_id=7, keep_jti="nothing")

    assert await auth_mod.session_is_idle("theirs") is False


@pytest.mark.asyncio
async def test_the_index_keeps_only_the_surviving_session(redis):
    """Otherwise the set grows for the life of the deployment."""
    for jti in ("a", "b", "c"):
        await auth_mod.start_session(jti, idle_minutes=30, user_id=7)
    await auth_mod.end_other_sessions(user_id=7, keep_jti="b")
    assert await redis.smembers(auth_mod._user_sessions_key(7)) == {"b"}


@pytest.mark.asyncio
async def test_redis_being_down_reports_nothing_ended_rather_than_raising(monkeypatch):
    async def no_redis():
        return None

    monkeypatch.setattr("app.core.redis_client.get_redis", no_redis)
    assert await auth_mod.end_other_sessions(user_id=7, keep_jti="x") == 0


@pytest.mark.asyncio
async def test_a_disabled_idle_window_still_indexes_the_session(redis):
    """idle_minutes=0 means "no idle timeout", not "this session is untrackable"
    — such a session must still be endable when a password changes."""
    await auth_mod.start_session("jti-a", idle_minutes=0, user_id=7)
    assert "jti-a" in await redis.smembers(auth_mod._user_sessions_key(7))


# --- the endpoint ---

@pytest.mark.asyncio
async def test_a_user_can_change_their_own_password(redis):
    from app.core.auth import AuthenticatedUser, get_password_hash, verify_password
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.auth import change_password
    from app.schemas.auth import PasswordChangeRequest

    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"self_{suffix}", email=f"self_{suffix}@company.local",
                    hashed_password=get_password_hash("Original-Pass-1"),
                    role="viewer", is_active=True)
        db.add(user)
        await db.commit()
        uid = user.id
        actor = AuthenticatedUser(user_id=uid, username=user.username,
                                  email=user.email, role=user.role)
        try:
            await change_password(
                PasswordChangeRequest(old_password="Original-Pass-1",
                                      new_password="Replaced-Pass-2"),
                db, actor, None)
            await db.refresh(user)
            assert verify_password("Replaced-Pass-2", user.hashed_password)
            assert not verify_password("Original-Pass-1", user.hashed_password)
        finally:
            await db.execute(User.__table__.delete().where(User.id == uid))
            await db.commit()


@pytest.mark.asyncio
async def test_the_wrong_old_password_is_refused(redis):
    """Without this, a stolen token is a permanent account takeover."""
    from fastapi import HTTPException

    from app.core.auth import AuthenticatedUser, get_password_hash, verify_password
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.auth import change_password
    from app.schemas.auth import PasswordChangeRequest

    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"wrong_{suffix}", email=f"wrong_{suffix}@company.local",
                    hashed_password=get_password_hash("Original-Pass-1"),
                    role="viewer", is_active=True)
        db.add(user)
        await db.commit()
        uid = user.id
        actor = AuthenticatedUser(user_id=uid, username=user.username,
                                  email=user.email, role=user.role)
        try:
            with pytest.raises(HTTPException) as exc:
                await change_password(
                    PasswordChangeRequest(old_password="Not-The-Password",
                                          new_password="Replaced-Pass-2"),
                    db, actor, None)
            assert exc.value.status_code == 400
            await db.refresh(user)
            assert verify_password("Original-Pass-1", user.hashed_password)
        finally:
            await db.execute(User.__table__.delete().where(User.id == uid))
            await db.commit()


def test_the_endpoint_changes_only_the_callers_own_password():
    """It must take the user from the token, never a user_id from the body —
    otherwise it is an unauthenticated admin endpoint."""
    import inspect

    from app.routers.auth import change_password

    signature = inspect.signature(change_password)
    assert "user_id" not in signature.parameters
    src = inspect.getsource(change_password)
    assert "current_user.user_id" in src


def test_the_change_is_audited_without_the_password():
    import inspect

    from app.routers.auth import change_password

    src = inspect.getsource(change_password)
    assert "user.password_changed" in src
    # Split on the call, not the name: `from app.core.audit import
    # record_action` would otherwise put the whole body on the right-hand side.
    payload = src.split("await record_action(")[1]
    assert "new_password" not in payload, (
        "the new password must not reach the audit payload")


def test_the_endpoint_ends_other_sessions():
    import inspect

    from app.routers.auth import change_password

    assert "end_other_sessions" in inspect.getsource(change_password)
