"""FastAPI dependency injection utilities."""
from typing import Optional, AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db_session
from app.core.auth import decode_access_token, AuthenticatedUser
from app.core.rbac import Role, Permission, has_permission
from app.models.user import User

# HTTP Bearer scheme for JWT
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    Dependency to get the current authenticated user from JWT token.
    
    Args:
        credentials: Bearer token credentials
        
    Returns:
        AuthenticatedUser object
        
    Raises:
        HTTPException: If no valid token provided
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = await decode_access_token(token)
    
    user_id_str = payload.get("user_id") or payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    user_id = int(user_id_str)
    
    # Fetch user from database
    from app.core.database import get_db_context
    
    async with get_db_context() as session:
        result = await session.execute(
            text("SELECT id, username, email, role, is_active FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        user_row = result.fetchone()
        
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        # is_active is column index 4 (0-based)
        if not user_row[4]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        return AuthenticatedUser(
            user_id=user_row[0],
            username=user_row[1],
            email=user_row[2],
            role=user_row[3],
        )


async def get_current_active_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Ensure the current user is active."""
    return current_user


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency."""
    async for session in get_db_session():
        yield session


def require_roles(*roles: Role):
    """
    Dependency factory to require specific roles.
    
    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: AuthenticatedUser = Depends(require_roles(Role.ADMIN))):
            ...
    """
    async def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        user_role = Role(current_user.role)
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {[r.value for r in roles]}. Your role: {current_user.role}",
            )
        return current_user
    
    return role_checker


def require_permission(*permissions: Permission):
    """
    Dependency factory to require specific permissions.
    
    Usage:
        @router.post("/agents")
        async def create_agent(
            user: AuthenticatedUser = Depends(require_permissions(Permission.AGENT_WRITE))
        ):
            ...
    """
    async def permission_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        user_role = Role(current_user.role)

        # require_permission() with multiple permissions requires ALL of them (AND logic)
        missing = [p for p in permissions if not has_permission(user_role, p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {[p.value for p in missing]}",
            )
        return current_user
    
    return permission_checker


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    Get current user if authenticated, otherwise return None.
    Useful for endpoints that work differently for authenticated vs anonymous users.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# Aliases for convenience
require_role = require_roles
require_permissions = require_permission


# ---------------------------------------------------------------------------
# Rate limiting — Redis sliding window (requires auth upstream)
# ---------------------------------------------------------------------------

def rate_limit(
    requests_per_minute: int = 30,
    requests_per_hour: int = 500,
    burst_limit: int = 5,
):
    """
    Factory: creates a combined auth + permission + rate-limit dependency.

    Usage:
        @router.post("/chat", ...)
        async def chat(
            body: ChatRequest,
            current_user: AuthenticatedUser = Depends(
                rate_limit(requests_per_minute=30)(require_permission(Permission.TASK_EXECUTE))
            ),
        ):
            ...

    Or chain manually:
        rate_limit()(get_current_user)  # auth only
        rate_limit()(require_permission(Permission.TASK_EXECUTE))  # auth + perms
    """
    import functools
    import os
    import time

    from app.core.ratelimit import (
        check_rate_limit,
        check_concurrency_limit,
        release_concurrency,
        RateLimitExceeded,
        ConcurrencyLimitExceeded,
    )

    rpm_env = int(os.getenv("RATELIMIT_REQUESTS_PER_MINUTE", str(requests_per_minute)))
    rph_env = int(os.getenv("RATELIMIT_REQUESTS_PER_HOUR", str(requests_per_hour)))
    burst_env = int(os.getenv("RATELIMIT_BURST", str(burst_limit)))

    def make_rate_limited(auth_dependency):
        """Wrap any auth dependency with Redis rate limiting."""
        async def rate_limit_wrapper(
            _ratelimit_scope: None = None,  # filled by FastAPI from auth_dependency result
        ):
            # FastAPI injects the auth dependency result based on type annotation
            # The actual user resolution happens in auth_dependency
            pass

        # Build the actual FastAPI dependency by chaining manually
        async def endpoint(
            current_user: AuthenticatedUser = Depends(auth_dependency),
        ) -> AuthenticatedUser:
            user_id = current_user.user_id

            # Per-minute sliding window
            allowed, _, reset_at = await check_rate_limit(
                user_id, 60, rpm_env, "ratelimit:minute"
            )
            if not allowed:
                raise RateLimitExceeded(retry_after=max(1, reset_at - int(time.time())))

            # Per-hour sliding window
            allowed, _, reset_at = await check_rate_limit(
                user_id, 3600, rph_env, "ratelimit:hour"
            )
            if not allowed:
                raise RateLimitExceeded(retry_after=max(1, reset_at - int(time.time())))

            # Burst (in-flight concurrency)
            allowed, current = await check_concurrency_limit(
                user_id, burst_env, "concurrency"
            )
            if not allowed:
                raise ConcurrencyLimitExceeded(current=current)

            try:
                yield current_user
            finally:
                await release_concurrency(user_id)

        return endpoint

    return make_rate_limited
