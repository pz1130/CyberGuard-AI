import pytest
import pytest_asyncio

from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.conversation import Conversation
from app.models.user import User
from app.services.internal_agent import InternalAgentRunner


@pytest_asyncio.fixture
async def parent_conv_and_internal_agent():
    """Create a user, an internal agent config, a parent conversation; yield ids."""
    async with AsyncSessionLocal() as s:
        u = User(username="ia_test", email="ia_test@x", hashed_password="x",
                 role="admin", is_active=True)
        s.add(u); await s.commit(); await s.refresh(u)

        ag = AgentConfig(agent_name="ia_test_agent", kind="internal",
                          system_prompt="you are helpful", is_active=True,
                          permission_level="medium", tool_loop_max_steps=4, memory_window=10)
        s.add(ag); await s.commit(); await s.refresh(ag)

        parent = Conversation(user_id=u.id, title="parent")
        s.add(parent); await s.commit(); await s.refresh(parent)

        yield {"user_id": u.id, "agent_id": ag.id, "parent_id": parent.id}

        # Cleanup
        await s.execute(Conversation.__table__.delete().where(Conversation.user_id == u.id))
        await s.execute(AgentConfig.__table__.delete().where(AgentConfig.id == ag.id))
        await s.execute(User.__table__.delete().where(User.id == u.id))
        await s.commit()


@pytest.mark.asyncio
async def test_load_memory_returns_empty_when_no_slice(parent_conv_and_internal_agent):
    ids = parent_conv_and_internal_agent
    cfg = {"id": ids["agent_id"], "agent_name": "ia_test_agent",
           "system_prompt": "you are helpful", "llm_provider_id": None, "llm_model": None,
           "tool_loop_max_steps": 4, "memory_window": 10, "knowledge_base_id": None,
           "associated_skills": [], "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    msgs = await runner._load_memory(parent_conversation_id=ids["parent_id"])
    assert msgs == []


@pytest.mark.asyncio
async def test_save_then_load_memory_round_trip(parent_conv_and_internal_agent):
    ids = parent_conv_and_internal_agent
    cfg = {"id": ids["agent_id"], "agent_name": "ia_test_agent",
           "system_prompt": "you are helpful", "llm_provider_id": None, "llm_model": None,
           "tool_loop_max_steps": 4, "memory_window": 10, "knowledge_base_id": None,
           "associated_skills": [], "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    new_msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await runner._append_memory(parent_conversation_id=ids["parent_id"],
                                 user_id=ids["user_id"], messages=new_msgs)
    loaded = await runner._load_memory(parent_conversation_id=ids["parent_id"])
    assert loaded == new_msgs


@pytest.mark.asyncio
async def test_build_system_prompt_concatenates_skills(monkeypatch):
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "BASE",
           "associated_skills": [101, 102], "metadata_json": {},
           "permission_level": "medium"}

    async def fake_loader(ids):
        return {101: "skill A body", 102: "skill B body"}

    runner = InternalAgentRunner(cfg)
    monkeypatch.setattr(runner, "_load_skill_bodies", fake_loader)
    prompt = await runner._build_system_prompt()
    assert "BASE" in prompt and "skill A body" in prompt and "skill B body" in prompt


@pytest.mark.asyncio
async def test_build_tools_includes_kb_when_kb_set(monkeypatch):
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "",
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "knowledge_base_id": 7, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    async def fake_mcp(*_a, **_kw): return []
    monkeypatch.setattr(runner, "_load_mcp_tools", fake_mcp)
    tools = await runner._build_tools()
    names = [t["function"]["name"] for t in tools]
    assert "kb_search" in names
