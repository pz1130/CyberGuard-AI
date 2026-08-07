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
async def test_build_system_prompt_injects_episodes_when_enabled(monkeypatch):
    from unittest.mock import AsyncMock
    from app.services.internal_agent import InternalAgentRunner

    class FakeEp:
        async def recall(self, agent_id, task, top_k=3, provider_id=None):
            return ([{"task": "scan a host", "approach": "web_search→vuln_search",
                      "outcome": "found CVE-x"}], [0.0] * 1536)
        async def record(self, **kw):  # unused here
            pass
    monkeypatch.setattr("app.services.internal_agent.episodic_memory", FakeEp())

    cfg = {"id": 7, "agent_name": "x", "system_prompt": "BASE",
           "associated_skills": [], "metadata_json": {"enable_episodic": True},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    monkeypatch.setattr(runner, "_load_skill_bodies", AsyncMock(return_value={}))

    prompt = await runner._build_system_prompt("scan host 1.2.3.4")
    assert "过往成功经验" in prompt and "web_search→vuln_search" in prompt
    assert runner._episode_embedding is not None     # stashed for reuse


@pytest.mark.asyncio
async def test_episodic_record_on_completed_run(monkeypatch):
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    def tc(name, cid):
        return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments="{}"))
    step1 = SimpleNamespace(content="", tool_calls=[tc("web_search", "1")])
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=[step1, "done answer"]))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    recorded = {}
    class FakeEp:
        async def recall(self, agent_id, task, top_k=3, provider_id=None):
            return ([], None)
        async def record(self, agent_id, task, approach, outcome, success=True,
                         tool_count=0, embedding=None, provider_id=None):
            recorded.update(agent_id=agent_id, task=task, approach=approach,
                            outcome=outcome, success=success)
    monkeypatch.setattr(ia_mod, "episodic_memory", FakeEp())

    cfg = {"id": 7, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"enable_episodic": True},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="ok"))

    res = await runner.execute(task="scan host", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert recorded["approach"] == "web_search"      # distilled tool sequence
    assert recorded["agent_id"] == 7 and recorded["success"] is True
    assert recorded["outcome"] == "done answer"


@pytest.mark.asyncio
async def test_no_episodic_record_when_disabled(monkeypatch):
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    fake_router = SimpleNamespace(chat=AsyncMock(return_value="just answer"))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    called = {"record": 0}
    class FakeEp:
        async def recall(self, *a, **k): return ([], None)
        async def record(self, *a, **k): called["record"] += 1
    monkeypatch.setattr(ia_mod, "episodic_memory", FakeEp())

    cfg = {"id": 7, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert called["record"] == 0                      # disabled -> never records


@pytest.mark.asyncio
async def test_build_tools_includes_search_when_enabled(monkeypatch):
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "",
           "associated_skills": [], "metadata_json": {"enable_search": True},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    async def fake_mcp(*_a, **_kw): return []
    monkeypatch.setattr(runner, "_load_mcp_tools", fake_mcp)
    names = [t["function"]["name"] for t in await runner._build_tools()]
    assert "web_search" in names and "vuln_search" in names


@pytest.mark.asyncio
async def test_build_tools_excludes_search_when_disabled(monkeypatch):
    from app.services.internal_agent import InternalAgentRunner
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "",
           "associated_skills": [], "metadata_json": {}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    async def fake_mcp(*_a, **_kw): return []
    monkeypatch.setattr(runner, "_load_mcp_tools", fake_mcp)
    names = [t["function"]["name"] for t in await runner._build_tools()]
    assert "web_search" not in names and "vuln_search" not in names


@pytest.mark.asyncio
async def test_dispatch_vuln_search(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.services.internal_agent import InternalAgentRunner

    captured = {}
    class FakeSearch:
        async def web_search(self, query, limit=5):
            return []
        async def vuln_search(self, query, limit=5):
            captured["call"] = (query, limit)
            return [{"title": "Log4Shell", "url": "http://e", "source": "sploitus"}]
    monkeypatch.setattr("app.services.internal_agent.search_service", FakeSearch())

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "",
           "associated_skills": [], "metadata_json": {"enable_search": True},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    runner._mcp_by_name = {}
    call = SimpleNamespace(id="c1", function=SimpleNamespace(
        name="vuln_search", arguments=json.dumps({"query": "log4j", "limit": 3})))
    out = await runner._dispatch(call)
    assert captured["call"] == ("log4j", 3)
    assert "Log4Shell" in out


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


def test_fingerprint_is_argument_order_invariant():
    from app.services.internal_agent import InternalAgentRunner
    fp = InternalAgentRunner._fingerprint
    assert fp("t", '{"a": 1, "b": 2}') == fp("t", '{"b": 2, "a": 1}')
    assert fp("t", '{"a": 1}') != fp("t", '{"a": 2}')
    assert fp("t", "{}") != fp("other", "{}")
    # Unparseable arguments fall back to the raw string without crashing.
    assert fp("t", "not json") == fp("t", "not json")


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
async def test_loop_detection_aborts_after_reflector_budget(monkeypatch):
    """An agent that calls the same tool with identical args every step is
    nudged by the reflector, then aborted once the reflector budget is spent —
    instead of spinning until tool_loop_max_steps."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import (
        InternalAgentRunner, LOOP_DETECT_THRESHOLD, REFLECT_MAX,
    )
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    def tc():
        return SimpleNamespace(id="c1", function=SimpleNamespace(
            name="spin", arguments='{"x": 1}'))
    # The model is stubborn: every reasoning step it re-issues the same call.
    step = SimpleNamespace(content="", tool_calls=[tc()])
    fake_router = SimpleNamespace(chat=AsyncMock(return_value=step))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 20, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    dispatched = []
    async def fake_dispatch(call):
        dispatched.append(call.function.name)
        return "same result"
    monkeypatch.setattr(runner, "_dispatch", fake_dispatch)

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "error"
    assert "loop" in res["error"].lower()
    # Real dispatch only happens below the loop threshold; repeats are
    # short-circuited into reflector notices.
    assert len(dispatched) == LOOP_DETECT_THRESHOLD - 1
    # Aborted well before exhausting the 20-step budget.
    assert fake_router.chat.await_count <= LOOP_DETECT_THRESHOLD + REFLECT_MAX + 1


@pytest.mark.asyncio
async def test_loop_detection_recovers_when_model_changes_course(monkeypatch):
    """If the reflector nudge works and the model stops repeating, the turn
    completes normally rather than aborting."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner, LOOP_DETECT_THRESHOLD
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    def tc():
        return SimpleNamespace(id="c1", function=SimpleNamespace(
            name="spin", arguments='{"x": 1}'))
    step = SimpleNamespace(content="", tool_calls=[tc()])
    # Repeat enough to trip detection once, then answer.
    seq = [step] * LOOP_DETECT_THRESHOLD + ["recovered answer"]
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=seq))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 20, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="r"))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "recovered answer"


def test_tool_call_budget_derives_from_permission():
    from app.services.internal_agent import (
        InternalAgentRunner, TOOL_CALL_BUDGET_DEFAULT, TOOL_CALL_BUDGET_LIMITED,
    )
    base = {"id": 1, "agent_name": "x", "metadata_json": {},
            "tool_loop_max_steps": 8}
    low = InternalAgentRunner({**base, "permission_level": "low"})
    med = InternalAgentRunner({**base, "permission_level": "medium"})
    override = InternalAgentRunner({**base, "permission_level": "low",
                                    "tool_call_budget": 5})
    # Defaults track max_steps so the budget branch is reachable (audit #4).
    assert low.tool_call_budget == min(TOOL_CALL_BUDGET_LIMITED, 8 * 3)
    assert med.tool_call_budget == min(TOOL_CALL_BUDGET_DEFAULT, max(8 * 5, 16))
    assert override.tool_call_budget == 5            # explicit config wins


@pytest.mark.asyncio
async def test_tool_call_budget_caps_dispatch_and_forces_answer(monkeypatch):
    """Once the per-run tool-call budget is spent, no more tools are dispatched
    and the model is forced to answer from what it has — not hard-errored."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    n = {"i": 0}
    # A model that keeps requesting (distinct, so the loop guard never trips)
    # tools while tools are offered, and only answers once tools are withdrawn.
    async def fake_chat(*, messages, provider_id, model, tools, **kwargs):
        if not tools:
            return SimpleNamespace(content="final after budget", tool_calls=None)
        n["i"] += 1
        return SimpleNamespace(content="", tool_calls=[SimpleNamespace(
            id=f"c{n['i']}",
            function=SimpleNamespace(name="grep", arguments=f'{{"i": {n["i"]}}}'))])
    monkeypatch.setattr(ia_mod, "get_llm_router",
                        lambda: SimpleNamespace(chat=fake_chat))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 50, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium", "tool_call_budget": 3}
    runner = InternalAgentRunner(cfg)
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[
        {"type": "function", "function": {"name": "grep"}}]))
    dispatched = []
    async def fake_dispatch(call):
        dispatched.append(call.function.name)
        return "ok"
    monkeypatch.setattr(runner, "_dispatch", fake_dispatch)

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "final after budget"
    assert len(dispatched) == 3                      # exactly the budget, no more


@pytest.mark.asyncio
async def test_llm_error_self_recovers_on_retry(monkeypatch):
    """A transient LLM failure is retried (self-recovery) rather than failing
    the turn immediately."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ia_mod.asyncio, "sleep", AsyncMock())  # no real backoff
    ok = SimpleNamespace(content="recovered", tool_calls=None)
    chat = AsyncMock(side_effect=[RuntimeError("transient"), ok])
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(chat=chat))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "recovered"
    assert chat.await_count == 2                         # first failed, retry won


@pytest.mark.asyncio
async def test_llm_error_fails_after_exhausting_retries(monkeypatch):
    """Persistent LLM failures fail the turn after LLM_RETRY_MAX retries."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner, LLM_RETRY_MAX
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ia_mod.asyncio, "sleep", AsyncMock())
    chat = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(chat=chat))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    res = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert res["status"] == "failed"
    assert "boom" in res["error"]
    assert chat.await_count == LLM_RETRY_MAX + 1         # initial + retries


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
        InternalAgentRunner, CONTEXT_COMPACT_TOKENS, CONTEXT_KEEP_RECENT,
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
    assert runner._estimate_tokens(messages) > CONTEXT_COMPACT_TOKENS

    chat = AsyncMock(return_value="## Summary\ncondensed history")
    out = await runner._maybe_compact(messages, SimpleNamespace(chat=chat))

    assert chat.await_count == 1                        # summarizer invoked
    assert out[0]["content"] == "SYS"                   # system kept
    assert "## 对话摘要" in out[1]["content"]           # digest inserted
    assert "condensed history" in out[1]["content"]
    assert len(out) <= 2 + CONTEXT_KEEP_RECENT          # system + digest + recent
    assert runner._estimate_tokens(out) < runner._estimate_tokens(messages)


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
        def __init__(self, cfg, *, pre_approved=False):
            captured["cfg"] = cfg
            captured["pre_approved"] = pre_approved
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
    assert captured["cfg"]["agent_name"].startswith("exec_test_int_")

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


@pytest.mark.asyncio
async def test_execute_stream_no_tools_emits_text_then_done(parent_conv_and_internal_agent, monkeypatch):
    import app.services.internal_agent as ia_mod
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    ids = parent_conv_and_internal_agent

    # The loop streams the turn itself; there is no second, tool-less call.
    async def fake_events(*args, **kwargs):
        for piece in ["Hel", "lo!"]:
            yield {"type": "text", "delta": piece}
        yield {"type": "done", "content": "Hello!", "tool_calls": None,
               "finish_reason": "stop"}

    fake_router = SimpleNamespace(stream_chat_events=fake_events)
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    runner = ia_mod.InternalAgentRunner({
        "id": ids["agent_id"], "agent_name": "x", "system_prompt": "y",
        "permission_level": "medium", "tool_loop_max_steps": 4, "memory_window": 10,
    })
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[]))

    events = [ev async for ev in runner.execute_stream(
        task="hi", conversation_id=ids["parent_id"], user_id=ids["user_id"])]

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert "text" in types
    assert types[-1] == "done"
    text = "".join(e["content"] for e in events if e["type"] == "text")
    assert text == "Hello!"
    assert events[-1]["output"] == "Hello!"


@pytest.mark.asyncio
async def test_execute_stream_tool_then_answer(parent_conv_and_internal_agent, monkeypatch):
    import app.services.internal_agent as ia_mod
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    ids = parent_conv_and_internal_agent

    def tc(cid, name):
        return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments="{}"))

    turns = [
        [{"type": "done", "content": "", "tool_calls": [tc("c1", "kb_search")],
          "finish_reason": "tool_calls"}],
        [{"type": "text", "delta": "done "}, {"type": "text", "delta": "answer"},
         {"type": "done", "content": "done answer", "tool_calls": None,
          "finish_reason": "stop"}],
    ]

    async def fake_events(*args, **kwargs):
        for ev in turns.pop(0):
            yield ev

    fake_router = SimpleNamespace(stream_chat_events=fake_events)
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    runner = ia_mod.InternalAgentRunner({
        "id": ids["agent_id"], "agent_name": "x", "system_prompt": "y",
        "permission_level": "medium", "tool_loop_max_steps": 4, "memory_window": 10,
    })
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[{"type": "function"}]))
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="tool ok"))

    events = [ev async for ev in runner.execute_stream(
        task="hi", conversation_id=ids["parent_id"], user_id=ids["user_id"])]
    types = [e["type"] for e in events]

    assert types[0] == "start"
    assert "tool_call_start" in types
    assert "tool_call_end" in types
    assert types[-1] == "done"
    assert events[-1]["output"] == "done answer"
    assert len(events[-1]["tool_calls"]) == 1


@pytest.mark.asyncio
async def test_execute_stream_llm_error_emits_error(parent_conv_and_internal_agent, monkeypatch):
    import app.services.internal_agent as ia_mod
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    ids = parent_conv_and_internal_agent
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    runner = ia_mod.InternalAgentRunner({
        "id": ids["agent_id"], "agent_name": "x", "system_prompt": "y",
        "permission_level": "medium", "tool_loop_max_steps": 4, "memory_window": 10,
    })
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[]))

    events = [ev async for ev in runner.execute_stream(
        task="hi", conversation_id=ids["parent_id"], user_id=ids["user_id"])]
    assert events[-1]["type"] == "error"
    assert "boom" in events[-1]["content"]


@pytest.mark.asyncio
async def test_agent_executor_execute_stream_routes_internal(parent_conv_and_internal_agent, monkeypatch):
    import app.services.agent_executor as ae_mod

    async def fake_stream(self, task, conversation_id, user_id):
        yield {"type": "start", "agent_id": 1, "agent_name": "x"}
        yield {"type": "text", "content": "hi"}
        yield {"type": "done", "output": "hi", "execution_time": 0.1, "tool_calls": []}

    monkeypatch.setattr(ae_mod.InternalAgentRunner, "execute_stream", fake_stream)

    ids = parent_conv_and_internal_agent
    events = [ev async for ev in ae_mod.AgentExecutor().execute_stream(
        agent_id=ids["agent_id"], task="hi", user_id=ids["user_id"])]
    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Truncated tool calls (finish_reason == "length")
# ---------------------------------------------------------------------------

def _tool_step(name="scan", args='{"target": "10.0.0.0/8"}', finish_reason=None,
               call_id="c1"):
    """An assistant message carrying one tool call, optionally length-truncated."""
    from types import SimpleNamespace
    kwargs = {"content": "", "tool_calls": [SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=args))]}
    if finish_reason is not None:
        kwargs["finish_reason"] = finish_reason
    return SimpleNamespace(**kwargs)


@pytest.mark.asyncio
async def test_truncated_response_refuses_to_execute_its_tool_calls(monkeypatch):
    """A response cut off by the output token limit may carry tool arguments
    that parse and validate while being semantically incomplete. None may run."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    seq = [_tool_step(finish_reason="length"), "answer after retry"]
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=seq))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)

    dispatched = []
    async def never_called(call):
        dispatched.append(call.function.name)
        return "should not happen"
    monkeypatch.setattr(runner, "_dispatch", never_called)

    res = await runner.execute(task="go", conversation_id=None, user_id=1)

    assert dispatched == []                       # nothing executed
    assert res["status"] == "completed"            # model got to re-issue
    assert res["output"] == "answer after retry"
    assert "TRUNCATED_TOOL_CALL" in res["tool_calls"][0]["result_preview"]


@pytest.mark.asyncio
async def test_truncated_response_emits_reflection_event(monkeypatch):
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    seq = [_tool_step(finish_reason="length"), "done"]
    monkeypatch.setattr(ia_mod, "get_llm_router",
                        lambda: SimpleNamespace(chat=AsyncMock(side_effect=seq)))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="x"))

    events = [ev async for ev in runner._run_loop("go", None, 1)]
    reasons = [e.get("reason") for e in events if e["type"] == "reflection"]
    assert "truncated_tool_call" in reasons
    ends = [e for e in events if e["type"] == "tool_call_end"]
    assert ends and all(e["error"] for e in ends)


@pytest.mark.asyncio
async def test_normal_finish_reason_still_executes_tools(monkeypatch):
    """Guard against over-blocking: a normal stop must not be treated as truncated."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    seq = [_tool_step(finish_reason="tool_calls"), "final"]
    monkeypatch.setattr(ia_mod, "get_llm_router",
                        lambda: SimpleNamespace(chat=AsyncMock(side_effect=seq)))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    dispatch = AsyncMock(return_value="scan output")
    monkeypatch.setattr(runner, "_dispatch", dispatch)

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert dispatch.await_count == 1
    assert res["status"] == "completed"


# ---------------------------------------------------------------------------
# Termination contract: governance refusals stop the run
# ---------------------------------------------------------------------------

def _pool_tool(name):
    """A Tool-pool row shaped the way _build_tools expects.

    Tagged "observe" so the before_tool governance chain lets it through — these
    tests are about what the loop does with execute_tool's *result*. Gate
    behaviour for pool tools is covered in test_internal_agent_governance.py.
    """
    from types import SimpleNamespace
    return SimpleNamespace(id=1, name=name, description="", input_schema_json=None,
                           command_template=f"{name} {{host}}",
                           action_category="observe", risk_tier="low",
                           rollback_command_template=None,
                           permission_level="medium")


def _wire_pool_tool(monkeypatch, runner, name):
    """Register one executable pool tool through the loaders.

    _build_tools() rebuilds _pool_tools_by_name on every run, so the fake has to
    be injected at the loader level rather than assigned onto the runner.
    """
    from unittest.mock import AsyncMock
    monkeypatch.setattr(runner, "_load_mcp_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(runner, "_load_pool_tools",
                        AsyncMock(return_value=[_pool_tool(name)]))


@pytest.mark.parametrize("tool_status,expected", [
    ("needs_approval", "needs_approval"),
    ("denied", "denied"),
    ("halted", "halted"),
])
@pytest.mark.asyncio
async def test_governance_refusal_terminates_the_run(monkeypatch, tool_status, expected):
    """A refusal must end the run, not become text the model can work around
    by reaching for a different tool."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    # The model would happily keep going if we let it.
    chat = AsyncMock(side_effect=[
        _tool_step(name="isolate_host", call_id="c1"),
        _tool_step(name="other_tool", call_id="c2"),
        "sneaky answer",
    ])
    monkeypatch.setattr(ia_mod, "get_llm_router",
                        lambda: SimpleNamespace(chat=chat))
    monkeypatch.setattr(ia_mod, "execute_tool",
                        AsyncMock(return_value={"status": tool_status,
                                                 "error": "refused by policy"}))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 10, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    _wire_pool_tool(monkeypatch, runner, "isolate_host")

    res = await runner.execute(task="isolate host h1", conversation_id=None, user_id=1)

    assert res["status"] == expected
    assert res["output"] is None
    # Stopped on the refusal — never asked the model for a follow-up move.
    assert chat.await_count == 1


@pytest.mark.asyncio
async def test_completed_tool_does_not_terminate_the_run(monkeypatch):
    """Guard against over-terminating: a successful tool keeps the loop going."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    chat = AsyncMock(side_effect=[_tool_step(name="grep"), "final answer"])
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(chat=chat))
    monkeypatch.setattr(ia_mod, "execute_tool",
                        AsyncMock(return_value={"status": "completed",
                                                 "stdout": "3 matches"}))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 10, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    _wire_pool_tool(monkeypatch, runner, "grep")

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert res["output"] == "final answer"


@pytest.mark.asyncio
async def test_terminated_run_is_not_recorded_as_a_successful_episode(monkeypatch):
    """A refused run must not be written to episodic memory as experience."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(
        chat=AsyncMock(return_value=_tool_step(name="isolate_host"))))
    monkeypatch.setattr(ia_mod, "execute_tool",
                        AsyncMock(return_value={"status": "denied", "error": "nope"}))
    recorder = AsyncMock()
    monkeypatch.setattr(ia_mod, "episodic_memory", SimpleNamespace(
        recall=AsyncMock(return_value=([], None)), record=recorder))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "enable_episodic": True,
           "metadata_json": {"mcp_tool_ids": []}, "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    _wire_pool_tool(monkeypatch, runner, "isolate_host")

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "denied"
    assert recorder.await_count == 0


@pytest.mark.asyncio
async def test_terminated_run_surfaces_on_the_streaming_path(monkeypatch):
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(
        chat=AsyncMock(return_value=_tool_step(name="isolate_host"))))
    monkeypatch.setattr(ia_mod, "execute_tool", AsyncMock(
        return_value={"status": "needs_approval", "error": "approval required"}))

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    runner = InternalAgentRunner(cfg)
    _wire_pool_tool(monkeypatch, runner, "isolate_host")

    events = [ev async for ev in runner.execute_stream("go", None, 1)]
    assert events[-1]["type"] == "error"
    assert events[-1]["status"] == "needs_approval"


# ---------------------------------------------------------------------------
# Episodic memory records how the run actually ended
# ---------------------------------------------------------------------------

def _episodic_runner(monkeypatch, chat_seq, **overrides):
    """A runner with episodic memory on and a recording spy attached."""
    from app.services import internal_agent as ia_mod
    from app.services.internal_agent import InternalAgentRunner
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(
        chat=AsyncMock(side_effect=chat_seq)))
    recorded = {}

    class Spy:
        async def recall(self, *a, **kw):
            return ([], None)
        async def record(self, agent_id, task, approach, outcome, success=True,
                         tool_count=0, embedding=None, provider_id=None):
            recorded.update(success=success, approach=approach, outcome=outcome)
    monkeypatch.setattr(ia_mod, "episodic_memory", Spy())

    cfg = {"id": 7, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 20, "memory_window": 0,
           "associated_skills": [], "enable_episodic": True,
           "metadata_json": {"mcp_tool_ids": []}, "permission_level": "medium"}
    cfg.update(overrides)
    return InternalAgentRunner(cfg), recorded


@pytest.mark.asyncio
async def test_clean_run_is_recorded_as_successful(monkeypatch):
    from unittest.mock import AsyncMock
    runner, recorded = _episodic_runner(
        monkeypatch, [_tool_step("grep"), "clean answer"])
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="3 matches"))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert recorded["success"] is True


@pytest.mark.asyncio
async def test_run_that_hit_a_tool_error_is_not_recorded_as_success(monkeypatch):
    """An answer produced despite failing tools is not experience worth
    replaying to future runs."""
    from unittest.mock import AsyncMock
    runner, recorded = _episodic_runner(
        monkeypatch, [_tool_step("grep"), "answer despite failure"])
    monkeypatch.setattr(runner, "_dispatch",
                        AsyncMock(return_value="ERROR: tool blew up"))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"      # user still gets an answer
    assert recorded["success"] is False      # but it is not replayed as success


@pytest.mark.asyncio
async def test_run_that_looped_is_not_recorded_as_success(monkeypatch):
    from unittest.mock import AsyncMock
    from app.services.internal_agent import LOOP_DETECT_THRESHOLD

    seq = [_tool_step("spin")] * LOOP_DETECT_THRESHOLD + ["recovered answer"]
    runner, recorded = _episodic_runner(monkeypatch, seq)
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="same"))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert recorded["success"] is False


@pytest.mark.asyncio
async def test_run_with_truncated_tool_calls_is_not_recorded_as_success(monkeypatch):
    from unittest.mock import AsyncMock
    runner, recorded = _episodic_runner(
        monkeypatch, [_tool_step(finish_reason="length"), "answer after retry"])
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="x"))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)
    assert res["status"] == "completed"
    assert recorded["success"] is False


@pytest.mark.asyncio
async def test_degraded_reasons_are_reported_on_answer_ready(monkeypatch):
    from unittest.mock import AsyncMock
    runner, _ = _episodic_runner(
        monkeypatch, [_tool_step("grep"), "answer"])
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="ERROR: nope"))

    events = [ev async for ev in runner._run_loop("go", None, 1)]
    answer = next(e for e in events if e["type"] == "answer_ready")
    assert answer["degraded_reasons"] == ["tool_error"]


@pytest.mark.asyncio
async def test_plain_string_error_results_are_still_flagged_as_errors(monkeypatch):
    """Regression: the untrusted-content fence prepends a tag, so classifying
    the *fenced* text hid the ERROR:/LOOP_DETECTED: prefixes that MCP, kb_search
    and the search tools use to report failure."""
    from unittest.mock import AsyncMock
    runner, _ = _episodic_runner(monkeypatch, [_tool_step("mcp_call"), "answer"])
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(
        return_value="ERROR: MCP tool 'mcp_call' failed: connection refused"))

    events = [ev async for ev in runner._run_loop("go", None, 1)]
    end = next(e for e in events if e["type"] == "tool_call_end")
    assert end["error"] is True
    # ...and the content still reaches the model fenced.
    assert end["result_preview"].startswith("<untrusted_tool_output")
