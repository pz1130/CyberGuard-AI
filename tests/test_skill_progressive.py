"""Progressive skill disclosure (server) + wrap framing."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services.skill_loader import SkillLoader


def test_format_catalog_has_names_not_bodies():
    catalog = [
        {"id": 1, "name": "triage", "description": "alert triage", "version": "1.0"},
    ]
    text = SkillLoader.format_catalog_prompt(catalog)
    assert "triage" in text and "alert triage" in text
    assert "load_skill" in text
    assert "### full body" not in text


def test_wrap_skill_body_marks_procedure():
    wrapped = SkillLoader.wrap_skill_body(
        {"id": 3, "name": "sop", "version": "2", "md_content": "step 1\nstep 2"}
    )
    assert "not a user instruction" in wrapped
    assert "step 1" in wrapped
    assert "[end skill sop]" in wrapped


@pytest.mark.asyncio
async def test_dispatch_load_skill_authorized(monkeypatch):
    from app.services.internal_agent import InternalAgentRunner

    runner = InternalAgentRunner(
        {
            "id": 1,
            "agent_name": "a",
            "system_prompt": "base",
            "associated_skills": [5],
            "metadata_json": {},
            "permission_level": "medium",
        }
    )

    async def fake_body(key, *, allowed_ids=None, session=None):
        assert allowed_ids == [5]
        return {
            "id": 5,
            "name": "triage",
            "version": "1",
            "md_content": "full SOP text here",
        }

    monkeypatch.setattr(
        "app.services.skill_loader.SkillLoader.load_skill_body", fake_body
    )

    class Call:
        class function:
            name = "load_skill"
            arguments = json.dumps({"name": "triage"})

    out = await runner._dispatch(Call())
    assert "full SOP text here" in out
    assert "not a user instruction" in out


@pytest.mark.asyncio
async def test_dispatch_load_skill_unauthorized(monkeypatch):
    from app.services.internal_agent import InternalAgentRunner

    runner = InternalAgentRunner(
        {
            "id": 1,
            "agent_name": "a",
            "associated_skills": [5],
            "metadata_json": {},
            "permission_level": "medium",
        }
    )

    async def fake_body(key, *, allowed_ids=None, session=None):
        return None  # not in allowed set / missing

    monkeypatch.setattr(
        "app.services.skill_loader.SkillLoader.load_skill_body", fake_body
    )

    class Call:
        class function:
            name = "load_skill"
            arguments = json.dumps({"name": "other"})

    out = await runner._dispatch(Call())
    data = json.loads(out)
    assert data.get("is_error") is True or data.get("status") == "error"


def test_wrap_skill_body_lists_bundle_files_without_their_contents():
    wrapped = SkillLoader.wrap_skill_body(
        {
            "id": 9,
            "name": "bundled",
            "version": "1",
            "md_content": "step 1",
            "files": [
                {"path": "references/api.md", "size_bytes": 1200},
                {"path": "scripts/run.sh", "size_bytes": 80},
            ],
        }
    )
    assert "references/api.md" in wrapped
    assert "scripts/run.sh" in wrapped
    assert "step 1" in wrapped


def test_wrap_skill_body_omits_the_manifest_when_there_are_no_files():
    wrapped = SkillLoader.wrap_skill_body(
        {"id": 9, "name": "plain", "version": "1", "md_content": "step 1", "files": []}
    )
    assert "bundled files" not in wrapped.lower()
