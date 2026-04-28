"""FastAPI dependency injection utilities."""
from typing import Optional, AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

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
    payload = decode_access_token(token)
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
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
        
        if not has_permission(user_role, permissions[0]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required permissions: {[p.value for p in permissions]}",
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