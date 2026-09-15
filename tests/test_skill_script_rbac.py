"""Uploading a script and letting it execute must be separately revocable."""
from __future__ import annotations

from app.core.rbac import Permission, Role, ROLE_PERMISSIONS, has_permission


def test_only_admin_may_approve_skill_scripts():
    for role in Role:
        expected = role is Role.ADMIN
        assert has_permission(role, Permission.SKILL_SCRIPT_APPROVE) is expected


def test_approval_is_not_implied_by_skill_write():
    # They happen to coincide on ADMIN today. The point is that a future role
    # can hold SKILL_WRITE without silently gaining code execution.
    for role, perms in ROLE_PERMISSIONS.items():
        if Permission.SKILL_WRITE in perms and role is not Role.ADMIN:
            assert Permission.SKILL_SCRIPT_APPROVE not in perms
    assert Permission.SKILL_SCRIPT_APPROVE is not Permission.SKILL_WRITE
