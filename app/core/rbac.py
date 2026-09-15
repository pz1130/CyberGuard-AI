"""RBAC middleware and permission management."""
from enum import Enum
from typing import List, Set
from functools import wraps
from fastapi import HTTPException, status
from starlette.requests import Request


class Role(str, Enum):
    """Pre-defined roles."""
    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Permission(str, Enum):
    """Permission categories."""
    # User management
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # Agent management
    AGENT_READ = "agent:read"
    AGENT_WRITE = "agent:write"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"

    # Skill/Tool
    SKILL_READ = "skill:read"
    SKILL_WRITE = "skill:write"
    # Promoting a bundle script to an executable Tool. Deliberately separate
    # from SKILL_WRITE: uploading a script and granting it the right to run
    # must be two independently revocable capabilities.
    SKILL_SCRIPT_APPROVE = "skill:script_approve"

    # Knowledge base
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"

    # Tasks
    TASK_READ = "task:read"
    TASK_WRITE = "task:write"
    TASK_EXECUTE = "task:execute"

    # Audit
    AUDIT_READ = "audit:read"

    # Settings (env vars, system config)
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Admin (encryption key management)
    ADMIN_ALL = "admin:all"


# Role-permission mapping
ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        Permission.USER_READ, Permission.USER_WRITE, Permission.USER_DELETE,
        Permission.AGENT_READ, Permission.AGENT_WRITE, Permission.AGENT_DELETE, Permission.AGENT_EXECUTE,
        Permission.SKILL_READ, Permission.SKILL_WRITE, Permission.SKILL_SCRIPT_APPROVE,
        Permission.KNOWLEDGE_READ, Permission.KNOWLEDGE_WRITE,
        Permission.TASK_READ, Permission.TASK_WRITE, Permission.TASK_EXECUTE,
        Permission.AUDIT_READ,
        Permission.SETTINGS_READ, Permission.SETTINGS_WRITE,
        Permission.ADMIN_ALL,
    },
    Role.OPERATOR: {
        Permission.AGENT_READ, Permission.AGENT_EXECUTE,
        Permission.SKILL_READ,
        Permission.KNOWLEDGE_READ,
        Permission.TASK_READ, Permission.TASK_WRITE, Permission.TASK_EXECUTE,
    },
    Role.ANALYST: {
        Permission.AGENT_READ,
        Permission.SKILL_READ,
        Permission.KNOWLEDGE_READ,
        Permission.TASK_READ,
    },
    Role.VIEWER: {
        Permission.AGENT_READ,
        Permission.SKILL_READ,
        Permission.TASK_READ,
    },
    Role.AUDITOR: {
        Permission.AUDIT_READ,
        Permission.TASK_READ,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def has_any_permission(role: Role, permissions: List[Permission]) -> bool:
    """Check if a role has any of the given permissions."""
    return any(has_permission(role, p) for p in permissions)


def require_permissions(*permissions: Permission):
    """Decorator to require specific permissions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request = kwargs.get('request') or (args[0] if args else None)
            if not isinstance(request, Request):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found"
                )

            # Get user from request state (set by auth middleware)
            user = getattr(request.state, 'user', None)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )

            # Check permissions
            role = Role(user.get('role', 'viewer'))
            if not has_any_permission(role, permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Required: {[p.value for p in permissions]}"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_role(*roles: Role):
    """Decorator to require specific roles."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get('request') or (args[0] if args else None)
            if not isinstance(request, Request):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found"
                )

            user = getattr(request.state, 'user', None)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )

            user_role = Role(user.get('role', 'viewer'))
            if user_role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role denied. Required: {[r.value for r in roles]}"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator