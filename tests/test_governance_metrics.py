"""Tests for governance metrics verdict math."""
import pytest
from unittest.mock import AsyncMock, patch
from app.services import governance_metrics as gm


def test_verdict_pass_fail():
    assert gm._verdict("governance_violation_rate", 0.004) is True
    assert gm._verdict("governance_violation_rate", 0.02) is False
    assert gm._verdict("kill_switch_response_seconds", 1.2) is True
    assert gm._verdict("kill_switch_response_seconds", 4.0) is False
    assert gm._verdict("rollback_success_rate", 0.995) is True
    assert gm._verdict("audit_completeness", 1.0) is True
    assert gm._verdict("audit_completeness", 0.99) is False


def test_rate_helpers():
    assert gm._rate(0, 0) == 0.0
    assert gm._rate(1, 200) == 0.005


@pytest.mark.asyncio
async def test_collect_assembles_all_metrics():
    with patch.object(gm, "_governance_violation_rate", AsyncMock(return_value=0.004)), \
         patch.object(gm, "_human_override_rate", AsyncMock(return_value=0.05)), \
         patch.object(gm, "_kill_switch_response", AsyncMock(return_value=0.8)), \
         patch.object(gm, "_audit_completeness", AsyncMock(return_value=1.0)), \
         patch.object(gm, "_rollback_success_rate", AsyncMock(return_value=1.0)):
        report = await gm.collect(window_days=30)
    names = {m["name"] for m in report["metrics"]}
    assert names == {"governance_violation_rate", "human_override_rate",
                     "kill_switch_response_seconds", "audit_completeness",
                     "rollback_success_rate"}
    assert report["all_pass"] is True
    assert all("target" in m and "pass" in m for m in report["metrics"])
