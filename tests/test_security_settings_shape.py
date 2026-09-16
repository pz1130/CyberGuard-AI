"""The Security page must not offer switches that turn security off.

Five of its six settings were never read by anything. Three of those five were
booleans whose meaning would have been "store credentials in plaintext", "skip
permission checks" and "stop writing the audit trail" — actions a security
product should not offer at all. They are invariants, not configuration, so
wiring them up would have been building three back doors and fitting handles.

They are gone from the schema and the table. `max_login_attempts` was the one
dead setting worth keeping, because it names a real control, and it is now
enforced (see tests/test_login_lockout.py). `api_key_rotation_days` named a
feature that does not exist, so it went with the booleans.
"""
from __future__ import annotations

import pytest

REMOVED = ("encryption_enabled", "rbac_enabled", "audit_logging",
           "api_key_rotation_days")


@pytest.mark.parametrize("field", REMOVED)
def test_the_dead_settings_are_gone_from_the_write_schema(field):
    from app.routers.security import SecuritySettingsUpdate

    assert field not in SecuritySettingsUpdate.model_fields


@pytest.mark.parametrize("field", REMOVED)
def test_the_dead_settings_are_gone_from_the_read_schema(field):
    from app.routers.security import SecuritySettingsResponse

    assert field not in SecuritySettingsResponse.model_fields


@pytest.mark.parametrize("field", REMOVED)
def test_the_dead_settings_are_gone_from_the_table(field):
    from app.models.security_settings import SecuritySettings

    assert field not in SecuritySettings.__table__.columns


def test_what_remains_is_exactly_what_is_enforced():
    """Both survivors are read at request time by real code paths:
    _max_login_attempts and _idle_minutes in app/routers/auth.py."""
    from app.routers.security import SecuritySettingsUpdate

    assert set(SecuritySettingsUpdate.model_fields) == {
        "max_login_attempts", "session_timeout_minutes"}


def test_toggling_security_off_is_not_reachable_through_the_api():
    """Sending the old field must change nothing rather than quietly work."""
    from app.routers.security import SecuritySettingsUpdate

    body = SecuritySettingsUpdate.model_validate(
        {"rbac_enabled": False, "audit_logging": False, "max_login_attempts": 7})
    assert body.model_dump(exclude_unset=True) == {"max_login_attempts": 7}


def test_the_config_import_builds_a_row_the_model_accepts():
    """It previously passed aes_key_rotation_days, audit_enabled,
    rate_limit_per_minute and three more that are not columns — a TypeError
    waiting for anyone who used config import."""
    import inspect

    from app.routers.config import import_config

    # Comments are stripped: the fix explains in prose which names it removed,
    # and a check that matched prose would fail on its own documentation.
    code = "\n".join(
        line.split("#", 1)[0]
        for line in inspect.getsource(import_config).splitlines()
    )
    stale = [name for name in
             ("aes_key_rotation_days", "audit_enabled", "rate_limit_per_minute",
              "rate_limit_per_hour", "burst_limit", "max_concurrent_requests",
              *REMOVED)
             if name in code]
    assert stale == [], (
        f"config import still writes fields the model does not have: {stale}")
