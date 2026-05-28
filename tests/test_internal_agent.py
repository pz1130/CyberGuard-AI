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


@pytest.mark.asyncio
async def test_dispatch_kb_search(monkeypatch):
    import json
    from app.services.internal_agent import InternalAgentRunner

    captured = {}
    class FakeKB:
        async def search(self, kb_id, query, top_k):
            captured["call"] = (kb_id, query, top_k)
            return ["chunk1", "chunk2"]
    monkeypatch.setattr("app.services.internal_agent.knowledge_service", FakeKB())

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "", "knowledge_base_id": 9,
           "associated_skills": [], "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    runner._mcp_by_name = {}

    from types import SimpleNamespace
    call = SimpleNamespace(
        function=SimpleNamespace(name="kb_search",
                                  arguments=json.dumps({"query": "foo", "top_k": 3})),
        id="c1",
    )
    out = await runner._dispatch(call)
    assert captured["call"] == (9, "foo", 3)
    assert "chunk1" in out


@pytest.mark.asyncio
async def test_execute_high_permission_returns_needs_approval():
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "", "permission_level": "high",
           "associated_skills": [], "metadata_json": {}}
    runner = InternalAgentRunner(cfg)
    res = await runner.execute(task="t", conversation_id=None, user_id=1)
    assert res["status"] == "needs_approval"


@pytest.mark.asyncio
async def test_execute_loop_terminates_on_final_message(monkeypatch):
    """Mock llm_router.chat to return a final message (no tool_calls); verify happy path."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    fake_msg = SimpleNamespace(content="final answer", tool_calls=None)
    fake_router = SimpleNamespace(chat=AsyncMock(return_value=fake_msg))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys",
           "llm_provider_id": 1, "llm_model": "m", "tool_loop_max_steps": 2,
           "memory_window": 0, "associated_skills": [],
           "metadata_json": {"mcp_tool_ids": []}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "final answer"
