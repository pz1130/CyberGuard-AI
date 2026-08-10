"""AUTO_APPROVE is the master switch for the whole HITL boundary.

When it is on, ApprovalService.wait_for_decision resolves every request as
approved with approver_id=0 and no human involved — every gate in the product
(gatekeeper NEEDS_APPROVAL, high-permission tools, master dispatch) silently
becomes a no-op.

It shipped defaulting to True, with only a warnings.warn outside development.
A warning is the wrong control: it prints once, to stderr, and disappears under
a process manager, so the boundary could be off in production with nothing to
show for it. P1 says default deny; INV-25 says security degradation is loud or
it does not count.
"""
from __future__ import annotations

import pytest

from app.config import Settings


_KEYS = {
    "ENCRYPTION_KEY": "e" * 64,
    "SECRET_KEY": "s" * 64,
}


def test_auto_approve_is_off_by_default():
    assert Settings(**_KEYS).AUTO_APPROVE is False


def test_auto_approve_is_permitted_in_development():
    cfg = Settings(**_KEYS, ENVIRONMENT="development", AUTO_APPROVE=True)
    assert cfg.AUTO_APPROVE is True


@pytest.mark.parametrize("environment", ["production", "staging", "prod"])
def test_auto_approve_outside_development_is_a_hard_error(environment):
    with pytest.raises(ValueError) as ei:
        Settings(**_KEYS, ENVIRONMENT=environment, AUTO_APPROVE=True)
    assert "AUTO_APPROVE" in str(ei.value)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_non_development_is_fine_with_auto_approve_off(environment):
    cfg = Settings(**_KEYS, ENVIRONMENT=environment, REDIS_PASSWORD="not-the-default")
    assert cfg.AUTO_APPROVE is False
