"""Lock an account after repeated failed logins.

``security_settings.max_login_attempts`` has been editable on the Security page
since migration 013 and nothing read it, so the product shipped with no limit
on password guessing at all.

Three properties decide the design:

* **Counted per username, not per IP.** That is what the setting says, and it
  is what stops a sustained attack on one account. Limiting by source address
  is a different control and should not hide inside this one.
* **Unknown usernames are counted too.** If only real accounts could be locked,
  whether a lockout happened would tell an attacker which usernames exist.
* **Redis unavailable fails open**, matching ``is_token_revoked`` and
  ``session_is_idle``. Failing closed would bar every operator from an
  incident-response tool the moment Redis hiccups — a worse outcome than the
  brute-force window it would close.
"""
from __future__ import annotations

# Not configurable on purpose. A second knob is a second thing that can rot
# into the dead setting this module exists to fix; 15 minutes is long enough to
# make sustained guessing impractical and short enough that a locked-out
# operator is not blocked for an incident.
LOCKOUT_SECONDS = 15 * 60

# How long failures accumulate before the count decays on its own, so a couple
# of typos last week do not combine with one today into a lockout.
WINDOW_SECONDS = 15 * 60


def _normalize(username: str) -> str:
    return (username or "").strip().lower()


def _fail_key(username: str) -> str:
    return f"login:fail:{_normalize(username)}"


def _lock_key(username: str) -> str:
    return f"login:lock:{_normalize(username)}"


async def _redis():
    from app.core import redis_client

    try:
        return await redis_client.get_redis()
    except Exception:  # noqa: BLE001 - availability, not correctness
        return None


async def is_locked(username: str) -> bool:
    """Whether this account is currently barred from logging in."""
    redis = await _redis()
    if redis is None:
        return False
    try:
        return bool(await redis.exists(_lock_key(username)))
    except Exception:  # noqa: BLE001
        return False


async def record_failure(username: str, *, max_attempts: int) -> int:
    """Count one failed attempt; lock the account on reaching the limit.

    Returns the running count, or 0 when the feature is disabled or Redis is
    unavailable.
    """
    if not max_attempts or max_attempts <= 0:
        return 0
    redis = await _redis()
    if redis is None:
        return 0
    try:
        count = int(await redis.incr(_fail_key(username)))
        await redis.expire(_fail_key(username), WINDOW_SECONDS)
        if count >= max_attempts:
            await redis.set(_lock_key(username), "1", ex=LOCKOUT_SECONDS)
        return count
    except Exception:  # noqa: BLE001
        return 0


async def clear(username: str) -> None:
    """Forget the failures for this account, after a successful login."""
    redis = await _redis()
    if redis is None:
        return
    try:
        await redis.delete(_fail_key(username), _lock_key(username))
    except Exception:  # noqa: BLE001
        return
