"""Local executor uses skill catalog only (no full SOP body)."""
from __future__ import annotations

import pytest

from app.services.local_executor import LocalAgentExecutor


@pytest.mark.asyncio
async def test_local_prompt_is_catalog_not_full_body(monkeypatch):
    async def fake_catalog(agent_type, session=None):
        return [
            {
                "id": 1,
                "name": "triage_sop",
                "description": "triage alerts",
                "version": "1.0",
                "category": agent_type,
            }
        ]

    monkeypatch.setattr(
        "app.services.skill_loader.SkillLoader.load_catalog_for_agent_type",
        fake_catalog,
    )
    # If full-body load is still called, fail the test
    async def ban_full(*a, **k):
        raise AssertionError("must not load full skill bodies into local prompt")

    monkeypatch.setattr(
        "app.services.skill_loader.SkillLoader.load_skills_for_agent_type",
        ban_full,
    )

    ex = LocalAgentExecutor(llm_router=object())
    prompt = await ex._get_system_prompt("threat_intel")
    assert "威胁情报" in prompt or "threat" in prompt.lower() or "IOC" in prompt
    assert "triage_sop" in prompt
    assert "triage alerts" in prompt
    assert "load_skill" in prompt or "not" in prompt.lower()
    assert "FULL_BODY_SECRET" not in prompt
    # Must not call full-body loader (ban_full would have raised)



@pytest.mark.asyncio
async def test_local_prompt_falls_back_when_catalog_fails(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.services.skill_loader.SkillLoader.load_catalog_for_agent_type",
        boom,
    )
    ex = LocalAgentExecutor(llm_router=object())
    prompt = await ex._get_system_prompt("general")
    assert "CyberGuard" in prompt or "安全" in prompt
