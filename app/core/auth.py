"""Authentication utilities and JWT handling."""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = settings.ALGORITHM


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
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
        return await redis.sismember("token:blacklist", jti)
    return False


async def revoke_token(jti: str, remaining_ttl_seconds: int) -> None:
    """
    Add a token's JTI to the revocation blacklist.
    Stores in Redis with TTL so the entry auto-expires when the token would have expired anyway.
    """
    from app.core.redis_client import get_redis
    redis = await get_redis()
    if redis:
        # TTL must be positive — don't bother storing if token is already expired
        if remaining_ttl_seconds > 0:
            await redis.sadd("token:blacklist", jti)
            await redis.expire("token:blacklist", remaining_ttl_seconds + 60)  # 60s grace period


async def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token. Returns None if invalid or revoked."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            revoked = await is_token_revoked(jti)
            if revoked:
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
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode = data.copy()
    import uuid
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh", "jti": str(uuid.uuid4())})
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
