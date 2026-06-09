"""Tests for the safety envelope service."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services import safety_envelope as se


def _tool(**kw):
    base = dict(id=1, name="isolator", action_category="contain_hard",
                input_schema_json=json.dumps({"type": "object",
                    "properties": {"host": {"type": "string"}}, "required": ["host"]}),
                rollback_command_template="unisolate {host}",
                validation_command_template=None, verification_command_template=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_requires_envelope():
    assert se.requires_envelope("contain_hard") is True
    assert se.requires_envelope("remediate") is True
    assert se.requires_envelope("observe") is False


def test_has_rollback():
    assert se.has_rollback(_tool()) is True
    assert se.has_rollback(_tool(rollback_command_template=None)) is False


@pytest.mark.asyncio
async def test_register_rollback_persists_argv():
    captured = {}
    async def fake_save(reg): captured.update(reg)
    with patch.object(se, "_save_registration", AsyncMock(side_effect=fake_save)):
        await se.register_rollback("act-1", _tool(), {"host": "h1"}, ttl_seconds=60)
    assert captured["rollback_argv"] == ["unisolate", "h1"]
    assert captured["action_id"] == "act-1"


@pytest.mark.asyncio
async def test_execute_rollback_pages_oncall_on_failure():
    reg = SimpleNamespace(action_id="act-2", tool_name="isolator",
                          rollback_argv=["unisolate", "h1"], status="registered")
    with patch.object(se, "_load_registration", AsyncMock(return_value=reg)), \
         patch.object(se, "_mark", AsyncMock()), \
         patch.object(se, "run_command", AsyncMock(return_value={"exit_code": 1, "stderr": "boom"})), \
         patch.object(se, "_page_oncall", AsyncMock()) as page:
        ok = await se.execute_rollback("act-2")
    assert ok is False
    page.assert_awaited()
