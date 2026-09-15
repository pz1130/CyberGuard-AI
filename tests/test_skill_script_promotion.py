"""Promotion is the gate that makes a bundle script executable."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.skills import validate_promotion
from app.schemas.skill import SkillScriptPromoteRequest


class _Row:
    def __init__(self, path, text):
        self.path, self.content_text, self.content_blob = path, text, None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt):
        return _Result(self.rows)


def _body(**over):
    base = dict(
        name="triage-script", description="triage an alert",
        command_template="python3 scripts/triage.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        required_permission=None, action_category="observe", risk_tier="low",
        permission_level="medium", timeout_seconds=60, script_network="none",
    )
    base.update(over)
    return SkillScriptPromoteRequest(**base)


BUNDLE = [_Row("scripts/triage.py", "print('ok')"), _Row("refs/a.md", "doc")]


@pytest.mark.asyncio
async def test_promotion_pins_the_bundle_digest():
    data = await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py", _body())
    assert data["source_skill_id"] == 1
    assert data["source_script_path"] == "scripts/triage.py"
    assert len(data["source_bundle_digest"]) == 64
    assert data["script_network"] == "none"


@pytest.mark.asyncio
async def test_promotion_refuses_a_script_not_in_the_bundle():
    with pytest.raises(HTTPException, match="not in the bundle"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/nope.py", _body())


@pytest.mark.asyncio
async def test_promotion_refuses_a_non_executable_extension():
    with pytest.raises(HTTPException, match="executable"):
        await validate_promotion(_DB(BUNDLE), 1, "refs/a.md",
                                 _body(command_template="python3 refs/a.md"))


@pytest.mark.asyncio
async def test_promotion_refuses_a_disallowed_interpreter():
    with pytest.raises(HTTPException, match="interpreter"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(command_template="bash scripts/triage.py {target}"))


@pytest.mark.asyncio
async def test_promotion_refuses_interpreter_flags():
    with pytest.raises(HTTPException, match="flag"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(command_template="python3 -c print(1)"))


@pytest.mark.asyncio
async def test_promotion_refuses_a_template_pointing_at_another_script():
    with pytest.raises(HTTPException, match="must run"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(command_template="python3 refs/a.md {target}"))


@pytest.mark.asyncio
async def test_promotion_refuses_allowlist_networking_in_phase_1():
    with pytest.raises(HTTPException, match="not supported"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(script_network="allowlist"))


@pytest.mark.asyncio
async def test_promotion_refuses_a_placeholder_absent_from_the_schema():
    # build_argv already enforces this; failing here means the approver sees it
    # at review time instead of at first execution.
    with pytest.raises(HTTPException):
        await validate_promotion(
            _DB(BUNDLE), 1, "scripts/triage.py",
            _body(command_template="python3 scripts/triage.py {undeclared}"))
