"""Unit tests for the SSO service's pure decision logic.

These cover the two functions that carry the real branching risk — Azure-claim →
app-role resolution and user provisioning/linking — without touching a DB, MSAL,
or the network.
"""
from dataclasses import dataclass
from typing import Optional

from app.services.sso_service import resolve_role, decide_provisioning


@dataclass
class _Mapping:
    azure_key: str
    app_role: str
    priority: int


@dataclass
class _User:
    is_active: bool = True


# ---- resolve_role ---------------------------------------------------------

def test_resolve_role_single_match():
    mappings = [_Mapping("grp-admins", "admin", 30)]
    claims = {"groups": ["grp-admins"]}
    assert resolve_role(mappings, claims, default_role="viewer") == "admin"


def test_resolve_role_highest_priority_wins():
    mappings = [
        _Mapping("grp-viewers", "viewer", 10),
        _Mapping("grp-admins", "admin", 30),
        _Mapping("grp-ops", "operator", 20),
    ]
    # user is in all three groups -> highest priority (admin) wins
    claims = {"groups": ["grp-viewers", "grp-admins", "grp-ops"]}
    assert resolve_role(mappings, claims, default_role="viewer") == "admin"


def test_resolve_role_matches_roles_claim_too():
    mappings = [_Mapping("App.Operator", "operator", 20)]
    claims = {"roles": ["App.Operator"]}  # app-role value, not a group id
    assert resolve_role(mappings, claims, default_role="viewer") == "operator"


def test_resolve_role_no_match_returns_default():
    mappings = [_Mapping("grp-admins", "admin", 30)]
    claims = {"groups": ["grp-unmapped"]}
    assert resolve_role(mappings, claims, default_role="viewer") == "viewer"


def test_resolve_role_no_claims_returns_default():
    assert resolve_role([], {}, default_role="viewer") == "viewer"


# ---- decide_provisioning --------------------------------------------------

def test_decide_existing_by_oid_is_used():
    u = _User(is_active=True)
    action, user = decide_provisioning(user_by_oid=u, user_by_email=None, allow_jit=True)
    assert action == "use" and user is u


def test_decide_link_by_email_when_only_email_matches():
    u = _User(is_active=True)
    action, user = decide_provisioning(user_by_oid=None, user_by_email=u, allow_jit=True)
    assert action == "link_email" and user is u


def test_decide_inactive_user_is_rejected():
    u = _User(is_active=False)
    action, user = decide_provisioning(user_by_oid=u, user_by_email=None, allow_jit=True)
    assert action == "reject_inactive"


def test_decide_jit_create_when_no_user_and_jit_allowed():
    action, user = decide_provisioning(user_by_oid=None, user_by_email=None, allow_jit=True)
    assert action == "create" and user is None


def test_decide_reject_when_no_user_and_jit_disabled():
    action, user = decide_provisioning(user_by_oid=None, user_by_email=None, allow_jit=False)
    assert action == "reject_no_jit"
