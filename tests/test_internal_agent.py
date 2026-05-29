import uuid

import pytest
import pytest_asyncio

from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.conversation import Conversation
from app.models.user import User
from app.services.internal_agent import InternalAgentRunner


@pytest_asyncio.fixture
async def parent_conv_and_internal_agent():
    """Create a user, an internal agent config, a parent conversation; yield ids.

    Uses a unique username/agent name per run so the shared (non-transactional)
    test DB can't trip unique constraints when a prior run left residue.
    """
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as s:
        u = User(username=f"ia_test_{uid}", email=f"ia_test_{uid}@x", hashed_password="x",
                 role="admin", is_active=True)
        s.add(u); await s.commit(); await s.refresh(u)

        ag = AgentConfig(agent_name=f"ia_test_agent_{uid}", kind="internal",
                          backend_type="openclaw",
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


def test_truncate_tool_result():
    from app.services.internal_agent import InternalAgentRunner, TOOL_RESULT_MAX_CHARS
    short = "ok"
    assert InternalAgentRunner._truncate_tool_result(short) == short
    big = "x" * (TOOL_RESULT_MAX_CHARS + 500)
    out = InternalAgentRunner._truncate_tool_result(big)
    assert len(out) < len(big)
    assert "truncated 500 chars" in out


@pytest.mark.asyncio
async def test_parallel_dispatch_runs_all_tools(monkeypatch):
    """A reasoning step with multiple tool_calls dispatches them all and feeds
    every result back before the next reasoning step."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    def tc(name, cid):
        return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments="{}"))

    step1 = SimpleNamespace(content="", tool_calls=[tc("a", "1"), tc("b", "2")])
    step2 = "all done"
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=[step1, step2]))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    dispatched = []
    async def fake_dispatch(call):
        dispatched.append(call.function.name)
        return f"result-{call.function.name}"
    monkeypatch.setattr(runner, "_dispatch", fake_dispatch)

    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "all done"
    assert sorted(dispatched) == ["a", "b"]            # both tools ran
    assert len(res["tool_calls"]) == 2                  # both logged


@pytest.mark.asyncio
async def test_auto_continue_nudges_text_only(monkeypatch):
    """A tool-equipped agent that answers without ever calling a tool is nudged
    up to AUTO_CONTINUE_MAX times before the text is accepted as final."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner, AUTO_CONTINUE_MAX
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    # Always text-only (tool_calls=None) so every pass triggers a nudge.
    reply = SimpleNamespace(content="answer", tool_calls=None)
    chat = AsyncMock(return_value=reply)
    fake_router = SimpleNamespace(chat=chat)
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 8, "memory_window": 0,
           "associated_skills": [], "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    # Give the agent a (fake) tool so auto-continue is eligible.
    async def fake_tools(): return [{"type": "function", "function": {"name": "t"}}]
    monkeypatch.setattr(runner, "_build_tools", fake_tools)

    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "answer"
    # AUTO_CONTINUE_MAX nudges + 1 final acceptance = MAX + 1 chat calls.
    assert chat.await_count == AUTO_CONTINUE_MAX + 1


@pytest.mark.asyncio
async def test_no_auto_continue_without_tools(monkeypatch):
    """An agent with no tools accepts a text-only answer immediately."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    chat = AsyncMock(return_value="just an answer")
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(chat=chat))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 8, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert chat.await_count == 1                        # no nudges


@pytest.mark.asyncio
async def test_maybe_compact_summarizes_when_oversized(monkeypatch):
    from app.services.internal_agent import (
        InternalAgentRunner, CONTEXT_COMPACT_CHARS, CONTEXT_KEEP_RECENT,
    )
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "", "llm_provider_id": 1,
           "llm_model": "m", "associated_skills": [], "metadata_json": {},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    # Build an oversized buffer: system + many big user/assistant turns.
    big = "y" * 2000
    messages = [{"role": "system", "content": "SYS"}]
    for i in range(20):
        messages.append({"role": "user", "content": big})
        messages.append({"role": "assistant", "content": big})
    assert runner._estimate_chars(messages) > CONTEXT_COMPACT_CHARS

    chat = AsyncMock(return_value="## Summary\ncondensed history")
    out = await runner._maybe_compact(messages, SimpleNamespace(chat=chat))

    assert chat.await_count == 1                        # summarizer invoked
    assert out[0]["content"] == "SYS"                   # system kept
    assert "## 对话摘要" in out[1]["content"]           # digest inserted
    assert "condensed history" in out[1]["content"]
    assert len(out) <= 2 + CONTEXT_KEEP_RECENT          # system + digest + recent
    assert runner._estimate_chars(out) < runner._estimate_chars(messages)


@pytest.mark.asyncio
async def test_maybe_compact_noop_when_small():
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "", "associated_skills": [],
           "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
    chat = AsyncMock()
    out = await runner._maybe_compact(messages, SimpleNamespace(chat=chat))
    assert out is messages                              # untouched
    assert chat.await_count == 0                        # summarizer not called


@pytest.mark.asyncio
async def test_agent_executor_routes_internal_kind(monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.core.database import AsyncSessionLocal
    from app.models.agent import AgentConfig

    async with AsyncSessionLocal() as s:
        ag = AgentConfig(agent_name=f"exec_test_int_{uuid.uuid4().hex[:8]}", kind="internal",
                          backend_type="openclaw",
                          system_prompt="sys", is_active=True,
                          permission_level="medium", tool_loop_max_steps=1)
        s.add(ag); await s.commit(); await s.refresh(ag)
        agent_id = ag.id

    captured = {}
    class FakeRunner:
        def __init__(self, cfg): captured["cfg"] = cfg
        async def execute(self, task, conversation_id, user_id):
            captured["task"] = task
            return {"status": "completed", "output": "ok",
                    "agent_id": agent_id, "agent_name": "exec_test_int"}
    monkeypatch.setattr("app.services.agent_executor.InternalAgentRunner",
                         FakeRunner, raising=False)

    ex = AgentExecutor()
    result = await ex.execute(agent_id=agent_id, task="hello", user_id=1,
                               context={"conversation_id": None})
    assert result["status"] == "completed"
    assert captured["task"] == "hello"
    assert captured["cfg"]["agent_name"] == "exec_test_int"

    async with AsyncSessionLocal() as s:
        await s.execute(AgentConfig.__table__.delete().where(AgentConfig.id == agent_id))
        await s.commit()


@pytest.mark.asyncio
async def test_internal_agent_dispatches_pool_tool(monkeypatch):
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    def tc(name, cid):
        return SimpleNamespace(id=cid, function=SimpleNamespace(
            name=name, arguments='{"msg": "hi"}'))
    step1 = SimpleNamespace(content="", tool_calls=[tc("echo_test", "1")])
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=[step1, "done"]))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "s", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"tool_ids": [42]},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    fake_tool = SimpleNamespace(id=42, name="echo_test", description="d",
                                input_schema_json='{"type":"object","properties":{"msg":{}}}',
                                command_template="echo {msg}", permission_level="medium",
                                required_permission=None, timeout_seconds=30)
    async def fake_load_pool_tools(): return [fake_tool]
    monkeypatch.setattr(runner, "_load_pool_tools", fake_load_pool_tools)
    monkeypatch.setattr(ia_mod, "execute_tool",
                        AsyncMock(return_value={"status": "completed", "stdout": "hi"}))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert any(c["name"] == "echo_test" for c in res["tool_calls"])


def test_runner_prefers_assignment_columns_over_metadata():
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x", "associated_skills": [1],
           "associated_tools": [2], "associated_mcp_tools": [3],
           "metadata_json": {"tool_ids": [9], "mcp_tool_ids": [8]},
           "permission_level": "medium"}
    r = InternalAgentRunner(cfg)
    assert r.associated_skills == [1]
    assert r.pool_tool_ids == [2]
    assert r.mcp_tool_ids == [3]


def test_runner_falls_back_to_metadata_when_columns_absent():
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x",
           "metadata_json": {"tool_ids": [9], "mcp_tool_ids": [8]},
           "permission_level": "medium"}
    r = InternalAgentRunner(cfg)
    assert r.pool_tool_ids == [9]
    assert r.mcp_tool_ids == [8]
