"""Authentication utilities and JWT handling."""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import bcrypt
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.config import settings

ALGORITHM = settings.ALGORITHM

# bcrypt hashes at most 72 bytes of input. Versions before 4.1 truncated
# silently; bcrypt >= 5 raises ValueError instead, which surfaced as a 500 on
# any long passphrase. We reject rather than truncate: truncating would mean a
# 200-character passphrase is silently no stronger than its first 72 bytes,
# which is exactly the kind of invisible downgrade P5 forbids. Pre-hashing
# (bcrypt_sha256) would remove the limit but invalidates every stored hash, so
# it belongs in a migration, not here.
BCRYPT_MAX_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds what bcrypt can actually hash."""

    def __init__(self, length: int):
        super().__init__(
            f"password is {length} bytes; bcrypt accepts at most "
            f"{BCRYPT_MAX_BYTES} bytes (UTF-8 encoded)"
        )
        self.length = length


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash. Never raises."""
    try:
        encoded = plain_password.encode("utf-8")
        if len(encoded) > BCRYPT_MAX_BYTES:
            # No stored hash can correspond to an over-length input, and
            # checkpw would raise rather than return False.
            return False
        return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt.

    Raises PasswordTooLongError so callers can return 400 instead of 500.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise PasswordTooLongError(len(encoded))
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    # Generate unique jti for revocation support
    import uuid
    to_encode["jti"] = str(uuid.uuid4())
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def is_token_revoked(jti: str) -> bool:
    """Check if a token's JTI is in the revocation blacklist (Redis)."""
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if redis:
        return await redis.exists(f"token:blacklist:{jti}")
    return False


async def revoke_token(jti: str, remaining_ttl_seconds: int) -> None:
    """
    Add a token's JTI to the revocation blacklist.
    Each JTI is stored as its own Redis key with independent TTL,
    avoiding the race condition where a shared SET TTL could be
    shortened by a short-lived token revocation.
    """
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if redis:
        # TTL must be positive — don't bother storing if token is already expired
        if remaining_ttl_seconds > 0:
            ttl = remaining_ttl_seconds + 60  # 60s grace period
            await redis.set(f"token:blacklist:{jti}", "1", ex=ttl)


# --- idle session tracking ---------------------------------------------------
#
# `security_settings.session_timeout_minutes` has been editable on the Security
# page since migration 013 and nothing read it. A browser-side timer would not
# have changed that: the token stays valid for ACCESS_TOKEN_EXPIRE_MINUTES, so
# whoever holds it still has a session.
#
# A session's liveness is one Redis key with a TTL. Only an explicit heartbeat
# refreshes it — never token verification — because the UI polls every 30
# seconds on every page, and a timeout that any request refreshed would never
# once fire.

def _session_key(jti: str) -> str:
    return f"session:active:{jti}"


async def start_session(jti: str, idle_minutes: int) -> None:
    """Mark a freshly issued token's session as live."""
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if redis and idle_minutes > 0:
        await redis.set(_session_key(jti), "1", ex=int(idle_minutes) * 60)


async def touch_session(jti: str, idle_minutes: int) -> bool:
    """Extend a live session. Returns False if there was nothing to extend.

    Deliberately not a `set`: an expired session must stay expired, or a tab
    left open overnight would come back to life on the next heartbeat.
    """
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if not redis or idle_minutes <= 0:
        return False
    return bool(await redis.expire(_session_key(jti), int(idle_minutes) * 60))


async def end_session(jti: str) -> None:
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if redis:
        await redis.delete(_session_key(jti))


async def session_is_idle(jti: str) -> bool:
    """Whether this session has gone quiet for longer than the configured window.

    Returns False when Redis is unavailable, matching `is_token_revoked`.
    Failing closed would sign out every user on a Redis blip; failing open falls
    back to the token's own expiry, which is the behaviour without this feature.
    """
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if not redis:
        return False
    return not await redis.exists(_session_key(jti))


async def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token. Returns None if invalid, revoked
    or idle."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            revoked = await is_token_revoked(jti)
            if revoked:
                return None
            # Absence is expiry, with no grandfathering. Creating the key here
            # when it is missing would let a background poll resurrect a session
            # that had already timed out — the one outcome this prevents.
            if await session_is_idle(jti):
                return None
        return payload
    except JWTError:
        return None


async def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token. Raises HTTPException if invalid."""
    payload = await verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a JWT refresh token with 7-day expiration."""
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode = data.copy()
    import uuid
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


async def verify_refresh_token(token: str) -> Dict[str, Any]:
    """Verify a refresh token and return its payload."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: expected refresh token",
        )
    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
    return payload


class AuthenticatedUser:
    """User object extracted from JWT token."""

    def __init__(self, user_id: int, username: str, email: str, role: str):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.role = role

    @property
    def is_active(self) -> bool:
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
        }


async def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user by username and password."""
    from app.core.database import get_db_context
    from sqlalchemy import text

    async with get_db_context() as session:
        result = await session.execute(
            text("SELECT id, username, email, hashed_password, role, is_active FROM users WHERE username = :username"),
            {"username": username}
        )
        user_row = result.fetchone()

        if not user_row:
            return None

        user_dict = {
            "id": user_row[0],
            "username": user_row[1],
            "email": user_row[2],
            "hashed_password": user_row[3],
            "role": user_row[4],
            "is_active": user_row[5],
        }

        if not user_dict["is_active"]:
            return None

        if not verify_password(password, user_dict["hashed_password"]):
            return None

        del user_dict["hashed_password"]
        return user_dict
