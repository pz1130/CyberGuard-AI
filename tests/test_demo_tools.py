"""Seeded demo tools must be executable and have a rollback for contain_hard."""
import asyncio

import pytest
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.skill import Skill, Tool
from app.services.demo_catalog import DEMO_SKILLS, DEMO_TOOLS, demo_tool_by_name
from app.services.demo_catalog import DEMO_AGENT_NAME, seed_demo_catalog_on_startup


def test_demo_tools_include_observe_and_contain():
    names = {t["name"] for t in DEMO_TOOLS}
    assert "simulate_observe" in names
    assert "simulate_block_ip" in names


def test_block_ip_is_governed_executable():
    tool = demo_tool_by_name("simulate_block_ip")
    assert "{ip}" in tool["command_template"]
    assert tool["rollback_command_template"]
    assert "{ip}" in tool["rollback_command_template"]
    assert tool["action_category"] == "contain_hard"
    assert tool["risk_tier"] == "high"
    assert tool["requires_approval"] is True
    assert "echo" in tool["command_template"]
    assert "SIMULATED" in tool["command_template"]


def test_observe_tool_does_not_require_approval():
    tool = demo_tool_by_name("simulate_observe")
    assert tool["action_category"] == "observe"
    assert tool["requires_approval"] is False
    assert tool["command_template"].startswith("echo")


def test_demo_skill_mentions_block_tool():
    skill = DEMO_SKILLS[0]
    assert "simulate_block_ip" in skill["md_content"]


@pytest.mark.asyncio
async def test_concurrent_demo_seed_is_idempotent():
    names = [tool["name"] for tool in DEMO_TOOLS]
    skill_names = [skill["name"] for skill in DEMO_SKILLS]
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentConfig).where(AgentConfig.agent_name == DEMO_AGENT_NAME))
        await session.execute(delete(Skill).where(Skill.name.in_(skill_names)))
        await session.execute(delete(Tool).where(Tool.name.in_(names)))
        await session.commit()

    await asyncio.gather(*(seed_demo_catalog_on_startup() for _ in range(4)))

    async with AsyncSessionLocal() as session:
        tool_count = (await session.execute(
            select(func.count(Tool.id)).where(Tool.name.in_(names))
        )).scalar_one()
        skill_count = (await session.execute(
            select(func.count(Skill.id)).where(Skill.name.in_(skill_names))
        )).scalar_one()
        agent_count = (await session.execute(
            select(func.count(AgentConfig.id)).where(AgentConfig.agent_name == DEMO_AGENT_NAME)
        )).scalar_one()

    assert tool_count == len(names)
    assert skill_count == len(skill_names)
    assert agent_count == 1
