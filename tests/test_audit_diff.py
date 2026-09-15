"""What a privileged change recorded in the audit trail.

The HTTP middleware already records that someone called PUT /users/3 and got a
200. It does not record the request body, deliberately — a blanket body log
would write passwords and API keys into the audit table, which is worse than
the gap it closes.

So the trail says a change happened but not what it was, and for the handful of
operations that move authority around, "what was it" is the question anyone
would actually ask. field_diff answers it without carrying the secrets.
"""
from __future__ import annotations

from app.core.audit_diff import REDACTED, field_diff


def test_only_changed_fields_appear():
    before = {"username": "amy", "role": "analyst", "is_active": True}
    after = {"username": "amy", "role": "admin", "is_active": True}
    assert field_diff(before, after) == {"role": {"from": "analyst", "to": "admin"}}


def test_an_unchanged_object_produces_nothing():
    same = {"role": "analyst"}
    assert field_diff(same, dict(same)) == {}


def test_a_newly_set_field_is_recorded():
    assert field_diff({}, {"role": "admin"}) == {"role": {"from": None, "to": "admin"}}


def test_a_cleared_field_is_recorded():
    assert field_diff({"role": "admin"}, {"role": None}) == {
        "role": {"from": "admin", "to": None}}


def test_fields_absent_from_the_update_are_left_alone():
    """A PATCH-shaped body must not read as "everything else was cleared"."""
    before = {"username": "amy", "role": "analyst"}
    after = {"role": "admin"}
    assert field_diff(before, after) == {"role": {"from": "analyst", "to": "admin"}}


def test_a_secret_records_that_it_changed_but_never_its_value():
    before = {"api_key": "sk-old-1234", "name": "vendor"}
    after = {"api_key": "sk-new-5678", "name": "vendor"}
    diff = field_diff(before, after)
    assert diff == {"api_key": {"from": REDACTED, "to": REDACTED}}
    assert "sk-old-1234" not in str(diff)
    assert "sk-new-5678" not in str(diff)


def test_every_credential_shaped_name_is_redacted():
    for key in ("password", "hashed_password", "api_key", "api_key_encrypted",
                "secret", "token", "env_vars", "env_vars_encrypted",
                "client_secret", "private_key"):
        diff = field_diff({key: "old"}, {key: "new"})
        assert diff[key] == {"from": REDACTED, "to": REDACTED}, key


def test_redaction_is_case_and_separator_insensitive():
    for key in ("API_KEY", "apiKey", "Api-Key"):
        assert field_diff({key: "a"}, {key: "b"})[key]["to"] is REDACTED, key


def test_an_unchanged_secret_is_not_reported_as_a_change():
    assert field_diff({"api_key": "same"}, {"api_key": "same"}) == {}


def test_long_values_are_truncated_so_one_field_cannot_flood_the_trail():
    long_value = "x" * 5000
    diff = field_diff({"note": "short"}, {"note": long_value})
    assert len(diff["note"]["to"]) < 1000


def test_nested_structures_survive_as_values():
    before = {"allowed_categories": ["observe"]}
    after = {"allowed_categories": ["observe", "mutate"]}
    assert field_diff(before, after) == {
        "allowed_categories": {"from": ["observe"], "to": ["observe", "mutate"]}}


# --- the operations that must carry a before/after ---

import inspect

import pytest


@pytest.mark.parametrize("module,handler,action", [
    ("app.routers.users", "update_user", "user.update"),
    ("app.routers.security", "put_settings", "security_settings.update"),
    ("app.routers.agents", "update_agent", "agent.governance_update"),
])
def test_privileged_writes_record_what_changed(module, handler, action):
    """The middleware records that the call happened; these record its content.

    Asserted on the source so a refactor that drops the record shows up here
    rather than as a quiet hole in the trail months later.
    """
    src = inspect.getsource(getattr(__import__(module, fromlist=["x"]), handler))
    assert "field_diff" in src, f"{handler} no longer diffs its change"
    assert action in src, f"{handler} no longer records {action!r}"


def test_a_password_change_is_recorded_without_the_password():
    from app.routers.users import update_user

    src = inspect.getsource(update_user)
    # The field is fed to field_diff, which redacts it — never logged raw.
    assert "hashed_password" in src
    assert "body.password" not in src.split("field_diff")[1], (
        "the raw password must not reach the audit payload"
    )
