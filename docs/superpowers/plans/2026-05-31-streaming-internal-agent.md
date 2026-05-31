# Streaming Internal Sub-Agent Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user run one internal sub-agent and watch it work live — final answer streamed token-by-token plus `tool_call_start`/`tool_call_end` lifecycle events — over SSE, with a minimal Agents-page UI consumer.

**Architecture:** Refactor `InternalAgentRunner`'s tool loop into a shared private async generator `_run_loop()` that yields semantic events (`start`, `tool_call_start`, `tool_call_end`, `answer_ready`, `error`). The existing batch `execute()` and a new `execute_stream()` both consume `_run_loop()`. Only `execute_stream()` re-streams the final answer via the router's existing `stream_chat()` (one extra LLM call on the final step, Approach 1 from the spec); batch callers are unaffected and pay no extra call. A new `POST /agents/{id}/execute/stream` endpoint runs in-process (no Celery) and emits SSE; non-internal agents fall back to a single batch `done` event.

**Tech Stack:** FastAPI `StreamingResponse` (SSE), async generators, OpenAI-compatible LLM router, pytest/pytest-asyncio, React + TypeScript (fetch + `ReadableStream`).

**Design spec:** `docs/superpowers/specs/2026-05-31-streaming-internal-agent-design.md`

**Deviation from spec (intentional):** The spec wording "`execute()` wraps `execute_stream()`" is replaced by a shared `_run_loop()` core consumed by both. Reason: full delegation would make every batch caller (group chat, master agent) pay the streaming path's extra final LLM call — a cost regression across the app. The shared-core structure keeps a single loop implementation while confining the extra call to the streaming path.

**Run tests with the project venv:** `python` is not on PATH. Use `.venv/bin/python -m pytest`. DB/Redis-backed tests need the stack up: `docker compose up -d postgres redis`.

---

## File Structure

- `app/services/internal_agent.py` (modify) — extract `_run_loop()`; rewrite `execute()` as a consumer; add `execute_stream()`.
- `app/services/agent_executor.py` (modify) — extract `_load_config_dict()`; add `execute_stream()` with the kind branch.
- `app/routers/agents.py` (modify) — add `POST /agents/{agent_id}/execute/stream`.
- `tests/test_internal_agent.py` (modify) — add streaming + parity tests.
- `tests/test_agent_stream_endpoint.py` (create) — endpoint SSE smoke test.
- `webui/src/api/client.ts` (modify) — add `executeAgentStream` async generator.
- `webui/src/pages/Agents.tsx` (modify) — add a run/test panel consuming the stream.

---

## Task 1: Extract `_run_loop()` and make `execute()` consume it (parity refactor)

This task is a pure refactor: behavior of `execute()` must not change. The existing tests in `tests/test_internal_agent.py` (`test_execute_loop_terminates_on_final_message`, `test_parallel_dispatch_runs_all_tools`, `test_auto_continue_nudges_text_only`, `test_no_auto_continue_without_tools`) are the safety net.

**Files:**
- Modify: `app/services/internal_agent.py` (the `execute()` method, currently at lines 386–523)
- Test: `tests/test_internal_agent.py` (existing tests guard parity)

- [ ] **Step 1: Run the existing internal-agent tests to establish the green baseline**

Run: `docker compose up -d postgres redis && .venv/bin/python -m pytest tests/test_internal_agent.py -v`
Expected: PASS (these need the DB). Note the count so you can confirm it's unchanged after the refactor.

- [ ] **Step 2: Add the `_run_loop()` async generator**

In `app/services/internal_agent.py`, add this method to `InternalAgentRunner` directly **above** the current `execute()` method (around line 386). It is the current loop body, lifted verbatim, but yielding events instead of building a dict, and it stops at `answer_ready` **without** appending the final assistant message or persisting (the consumer does that).

```python
    async def _run_loop(self, task: str, conversation_id: Optional[int],
                        user_id: int):
        """Shared tool-call loop. Yields semantic events:

          {"type": "start", "agent_id", "agent_name"}
          {"type": "tool_call_start", "name", "arguments", "call_id"}
          {"type": "tool_call_end", "name", "call_id", "result_preview", "error"}
          {"type": "answer_ready", "messages", "new_messages",
                                   "candidate_text", "tool_call_log"}   # terminal-ish
          {"type": "error", "status": "failed"|"error", "error", ["tool_call_log"]}

        On ``answer_ready`` the model is ready to produce the final answer but
        it has NOT been generated/streamed yet — the consumer finalizes it.
        Persistence is the consumer's job (batch uses candidate_text; stream
        re-generates), so this generator never writes memory.
        """
        system_prompt = await self._build_system_prompt()
        tools = await self._build_tools()
        await self._resolve_mcp_lookup()
        history = await self._load_memory(conversation_id)

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": task})

        new_messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
        tool_call_log: List[Dict[str, Any]] = []

        router = get_llm_router()
        tool_used_ever = False
        auto_continue_used = 0

        yield {"type": "start", "agent_id": self.agent_id, "agent_name": self.agent_name}

        for step in range(self.max_steps):
            messages = await self._maybe_compact(messages, router)

            try:
                msg = await router.chat(
                    messages=messages,
                    provider_id=self.llm_provider_id,
                    model=self.llm_model,
                    tools=tools if tools else None,
                )
            except Exception as e:
                yield {"type": "error", "status": "failed",
                       "error": f"LLM error at step {step}: {e}"}
                return

            if isinstance(msg, str):
                tool_calls = None
                text_only = True
                candidate_text = msg
            else:
                tool_calls = getattr(msg, "tool_calls", None)
                text_only = not tool_calls
                candidate_text = getattr(msg, "content", None) or ""

            if text_only:
                if tools and not tool_used_ever and auto_continue_used < AUTO_CONTINUE_MAX:
                    auto_continue_used += 1
                    messages.append({
                        "role": "user",
                        "content": "如果任务尚未完成，请调用相应工具继续；"
                                   "如果确认已完成，请直接给出最终答复。",
                    })
                    continue
                yield {"type": "answer_ready", "messages": messages,
                       "new_messages": new_messages,
                       "candidate_text": candidate_text,
                       "tool_call_log": tool_call_log}
                return

            tool_used_ever = True
            assistant_msg = {
                "role": "assistant",
                "content": getattr(msg, "content", None) or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name,
                                      "arguments": c.function.arguments},
                    } for c in tool_calls
                ],
            }
            messages.append(assistant_msg)
            new_messages.append(assistant_msg)

            for c in tool_calls:
                yield {"type": "tool_call_start", "name": c.function.name,
                       "arguments": c.function.arguments, "call_id": c.id}

            results = await asyncio.gather(*[self._dispatch(c) for c in tool_calls])
            for call, result_str in zip(tool_calls, results):
                result_str = self._truncate_tool_result(result_str)
                tool_call_log.append({"name": call.function.name,
                                       "arguments": call.function.arguments,
                                       "result_preview": result_str[:200]})
                tool_msg = {"role": "tool", "tool_call_id": call.id,
                            "content": result_str}
                messages.append(tool_msg)
                new_messages.append(tool_msg)
                yield {"type": "tool_call_end", "name": call.function.name,
                       "call_id": call.id, "result_preview": result_str[:200],
                       "error": result_str.startswith("ERROR")}

        yield {"type": "error", "status": "error",
               "error": f"exceeded tool_loop_max_steps ({self.max_steps})",
               "tool_call_log": tool_call_log}
```

- [ ] **Step 3: Replace the body of `execute()` so it consumes `_run_loop()`**

Replace the entire current `execute()` method (everything from `async def execute(self, task: str, conversation_id: Optional[int],` through the final `return {...}` at the end of the file) with this consumer. The returned dict shapes are identical to the originals (`needs_approval`, `failed`, `error`, `completed`).

```python
    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int) -> Dict[str, Any]:
        """Run the tool-call loop (batch). Returns same shape as SubAgentWrapper.execute()."""
        start = time.monotonic()
        self._user_id = user_id

        if self.permission_level == "high":
            return {
                "status": "needs_approval",
                "output": None,
                "error": "High permission internal agent requires approval",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": 0,
            }

        final_event = None
        async for ev in self._run_loop(task, conversation_id, user_id):
            if ev["type"] in ("answer_ready", "error"):
                final_event = ev
                break
            # start / tool_call_* events are not surfaced in batch mode

        if final_event is None or final_event["type"] == "error":
            if final_event and final_event.get("status") == "failed":
                return {
                    "status": "failed",
                    "output": None,
                    "error": final_event["error"],
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "execution_time": round(time.monotonic() - start, 2),
                }
            return {
                "status": "error",
                "output": None,
                "error": final_event["error"] if final_event else "no result produced",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": round(time.monotonic() - start, 2),
                "tool_calls": final_event.get("tool_call_log", []) if final_event else [],
            }

        # answer_ready: batch mode uses the candidate text directly (no re-stream)
        final_text = final_event["candidate_text"]
        new_messages = final_event["new_messages"]
        new_messages.append({"role": "assistant", "content": final_text})
        await self._append_memory(conversation_id, user_id, new_messages)

        return {
            "status": "completed",
            "output": final_text,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "execution_time": round(time.monotonic() - start, 2),
            "tool_calls": final_event["tool_call_log"],
        }
```

- [ ] **Step 4: Run the existing tests to verify parity (unchanged pass count)**

Run: `.venv/bin/python -m pytest tests/test_internal_agent.py -v`
Expected: PASS — same tests, same count as Step 1. If any fail, the refactor changed behavior; compare the failing assertion against the original dict shape and fix `execute()`.

- [ ] **Step 5: Commit**

```bash
git add app/services/internal_agent.py
git commit -m "refactor(internal-agent): extract _run_loop() shared core; execute() consumes it"
```

---

## Task 2: Add `InternalAgentRunner.execute_stream()`

**Files:**
- Modify: `app/services/internal_agent.py` (add method after `execute()`)
- Test: `tests/test_internal_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_internal_agent.py`. These reuse the existing `parent_conv_and_internal_agent` fixture and the `SimpleNamespace`/`AsyncMock` router pattern already used in the file. The fake router needs both `chat` (batch decision) and `stream_chat` (async generator).

```python
@pytest.mark.asyncio
async def test_execute_stream_no_tools_emits_text_then_done(parent_conv_and_internal_agent, monkeypatch):
    import app.services.internal_agent as ia_mod
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    ids = parent_conv_and_internal_agent

    async def fake_stream(*args, **kwargs):
        for piece in ["Hel", "lo!"]:
            yield piece

    # No tools -> first chat returns text-only -> answer_ready -> re-stream.
    fake_router = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="ignored batch text", tool_calls=None)),
        stream_chat=fake_stream,
    )
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

    step1 = SimpleNamespace(content="", tool_calls=[tc("c1", "kb_search")])
    step2 = SimpleNamespace(content="batch final", tool_calls=None)

    async def fake_stream(*args, **kwargs):
        yield "done answer"

    fake_router = SimpleNamespace(
        chat=AsyncMock(side_effect=[step1, step2]),
        stream_chat=fake_stream,
    )
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_internal_agent.py -k execute_stream -v`
Expected: FAIL with `AttributeError: 'InternalAgentRunner' object has no attribute 'execute_stream'`.

- [ ] **Step 3: Add `execute_stream()`**

Add this method to `InternalAgentRunner`, directly below `execute()`:

```python
    async def execute_stream(self, task: str, conversation_id: Optional[int],
                             user_id: int):
        """Run the tool-call loop, streaming SSE-shaped event dicts.

        Emits: start / tool_call_start / tool_call_end / text* / done / error.
        The final answer is re-generated via router.stream_chat() (tools=None) —
        Approach 1's one extra LLM call, confined to the streaming path.
        """
        start = time.monotonic()
        self._user_id = user_id

        if self.permission_level == "high":
            yield {"type": "error",
                   "content": "High permission internal agent requires approval"}
            return

        async for ev in self._run_loop(task, conversation_id, user_id):
            t = ev["type"]
            if t in ("start", "tool_call_start", "tool_call_end"):
                yield ev
            elif t == "error":
                yield {"type": "error", "content": ev["error"]}
                return
            elif t == "answer_ready":
                messages = ev["messages"]
                new_messages = ev["new_messages"]
                router = get_llm_router()
                parts: List[str] = []
                try:
                    async for delta in router.stream_chat(
                        messages=messages,
                        provider_id=self.llm_provider_id,
                        model=self.llm_model,
                    ):
                        parts.append(delta)
                        yield {"type": "text", "content": delta}
                except Exception as e:
                    yield {"type": "error", "content": f"stream error: {e}"}
                    return

                final_text = "".join(parts)
                new_messages.append({"role": "assistant", "content": final_text})
                await self._append_memory(conversation_id, user_id, new_messages)
                yield {"type": "done", "output": final_text,
                       "execution_time": round(time.monotonic() - start, 2),
                       "tool_calls": ev["tool_call_log"]}
                return
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_internal_agent.py -k execute_stream -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full internal-agent file to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/test_internal_agent.py -v`
Expected: PASS (Task 1 baseline + 3 new).

- [ ] **Step 6: Commit**

```bash
git add app/services/internal_agent.py tests/test_internal_agent.py
git commit -m "feat(internal-agent): add execute_stream() with SSE events + final re-stream"
```

---

## Task 3: Add `AgentExecutor.execute_stream()` with kind branch

**Files:**
- Modify: `app/services/agent_executor.py` (extract `_load_config_dict()` from `execute()` at lines 287–329; add `execute_stream()` after `execute()` which ends at line 356)
- Test: `tests/test_internal_agent.py` (add a dispatch test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_internal_agent.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_internal_agent.py -k execute_stream_routes_internal -v`
Expected: FAIL with `AttributeError: 'AgentExecutor' object has no attribute 'execute_stream'`.

- [ ] **Step 3: Extract `_load_config_dict()` from `execute()`**

In `app/services/agent_executor.py`, in the `AgentExecutor.execute()` method, the block from `# Fetch agent config from database` (line 287) through the construction of `config_dict` ending with `"streaming": getattr(agent_obj, "streaming", True),\n            }` (line 329) returns `config_dict` (or an error dict when the agent is missing). Move that block into a new method, and have `execute()` call it.

Add this method to `AgentExecutor` (above `execute()` at line 267):

```python
    async def _load_config_dict(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """Load an AgentConfig row into the plain config dict used by runners.

        Returns None if the agent does not exist.
        """
        from app.core.database import get_db_context
        from app.models.agent import AgentConfig
        from sqlalchemy import select

        async with get_db_context() as session:
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.id == agent_id)
            )
            agent_obj = result.scalar_one_or_none()
            if not agent_obj:
                return None

            return {
                "id": agent_obj.id,
                "agent_name": agent_obj.agent_name,
                "kind": agent_obj.kind,
                "backend_type": agent_obj.backend_type,
                "provider_id": agent_obj.provider_id,
                "llm_provider_id": agent_obj.llm_provider_id,
                "llm_model": agent_obj.llm_model,
                "endpoint_url": agent_obj.endpoint_url,
                "env_vars_encrypted": agent_obj.env_vars_encrypted,
                "system_prompt": agent_obj.system_prompt,
                "permission_level": getattr(agent_obj, "permission_level", "medium"),
                "tool_loop_max_steps": agent_obj.tool_loop_max_steps,
                "memory_window": agent_obj.memory_window,
                "knowledge_base_id": agent_obj.knowledge_base_id,
                "associated_skills": agent_obj.associated_skills,
                "associated_tools": agent_obj.associated_tools,
                "associated_mcp_tools": agent_obj.associated_mcp_tools,
                "metadata_json": agent_obj.metadata_json,
                "api_key": getattr(agent_obj, "api_key", "") or "",
                "auth_mode": getattr(agent_obj, "auth_mode", "api_key"),
                "streaming": getattr(agent_obj, "streaming", True),
            }
```

Then in `execute()`, replace the inline fetch block (lines 287–329, from `# Fetch agent config from database` through the closing `}` of `config_dict`) with:

```python
        config_dict = await self._load_config_dict(agent_id)
        if config_dict is None:
            return {
                "status": "error",
                "output": None,
                "error": f"Agent {agent_id} not found",
            }
```

Leave the rest of `execute()` (permission check, kind branch, result enrichment) unchanged. Ensure `Optional` and `Dict`, `Any` are imported at the top of the file (they are already used by `execute()`'s signature).

- [ ] **Step 4: Add `execute_stream()`**

Add this method to `AgentExecutor`, directly after `execute()` (after line 356):

```python
    async def execute_stream(self, agent_id: int, task: str, user_id: int,
                             context: Optional[Dict[str, Any]] = None):
        """Stream a sub-agent run as SSE-shaped event dicts.

        Internal agents stream natively. Non-internal agents run the batch
        path and emit a single done/error event so the frontend is uniform.
        """
        config_dict = await self._load_config_dict(agent_id)
        if config_dict is None:
            yield {"type": "error", "content": f"Agent {agent_id} not found"}
            return

        kind = config_dict.get("kind") or "external"
        if kind == "internal":
            runner = InternalAgentRunner(config_dict)
            conv_id = (context or {}).get("conversation_id")
            async for ev in runner.execute_stream(
                task=task, conversation_id=conv_id, user_id=user_id):
                yield ev
            return

        # Non-internal: run batch, surface result as a single event.
        result = await self.execute(
            agent_id=agent_id, task=task, user_id=user_id, context=context)
        if result.get("status") in ("completed", "success"):
            yield {"type": "done", "output": result.get("output"),
                   "execution_time": result.get("execution_time"),
                   "tool_calls": result.get("tool_calls", [])}
        else:
            yield {"type": "error",
                   "content": result.get("error") or "agent execution failed"}
```

- [ ] **Step 5: Run the test to verify it passes + full file**

Run: `.venv/bin/python -m pytest tests/test_internal_agent.py -v`
Expected: PASS (all prior tests + the new dispatch test). The `_load_config_dict` extraction must not break `test_agent_executor_routes_internal_kind`.

- [ ] **Step 6: Commit**

```bash
git add app/services/agent_executor.py tests/test_internal_agent.py
git commit -m "feat(agent-executor): add execute_stream() + extract _load_config_dict()"
```

---

## Task 4: Add `POST /agents/{agent_id}/execute/stream` endpoint

**Files:**
- Modify: `app/routers/agents.py` (add endpoint after `execute_agent` at line 390–413)
- Test: `tests/test_agent_stream_endpoint.py` (create)

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_agent_stream_endpoint.py`. This repo tests endpoints by calling the router function **directly** with a fake authenticated user (a `SimpleNamespace` exposing `.user_id` is enough — the endpoint only reads `current_user.user_id`) and draining the returned `StreamingResponse.body_iterator`. `AgentExecutor.execute_stream` is patched on its source class so no LLM/DB is needed. `check_prompt_sync("hi")` does not block, so the guardrail stays real.

```python
import pytest
from types import SimpleNamespace
from unittest.mock import patch


@pytest.mark.asyncio
async def test_execute_stream_endpoint_emits_sse():
    """execute_agent_stream returns text/event-stream and forwards executor
    events as SSE `data:` frames, ending with a done event."""
    from app.routers import agents as ag

    async def fake_stream(self, agent_id, task, user_id, context=None):
        yield {"type": "start", "agent_id": agent_id, "agent_name": "x"}
        yield {"type": "text", "content": "hi"}
        yield {"type": "done", "output": "hi", "execution_time": 0.1, "tool_calls": []}

    with patch("app.services.agent_executor.AgentExecutor.execute_stream", fake_stream):
        resp = await ag.execute_agent_stream(
            agent_id=1,
            body={"task": "hi"},
            current_user=SimpleNamespace(user_id=1),
        )

    assert resp.media_type == "text/event-stream"
    chunks = []
    async for c in resp.body_iterator:
        chunks.append(c if isinstance(c, str) else c.decode())
    body = "".join(chunks)
    assert '"type": "start"' in body
    assert '"type": "done"' in body
    assert body.count("data: ") == 3   # one SSE frame per event
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_stream_endpoint.py -v`
Expected: FAIL with `AttributeError: module 'app.routers.agents' has no attribute 'execute_agent_stream'` (the endpoint does not exist yet).

- [ ] **Step 3: Add the endpoint**

In `app/routers/agents.py`, add directly after the existing `execute_agent` function (after line 413):

```python
@router.post("/agents/{agent_id}/execute/stream")
async def execute_agent_stream(
    agent_id: int,
    body: dict,
    current_user: AuthenticatedUser = Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """流式向指定 Sub-Agent 派发任务（SSE）。

    事件: start / tool_call_start / tool_call_end / text / done / error。
    internal agent 逐字流式; 其它 kind 以单个 done 事件返回批量结果。
    """
    import json as _json
    from fastapi.responses import StreamingResponse
    from app.core.guardrails import check_prompt_sync
    from app.services.agent_executor import AgentExecutor

    task = body.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="'task' 字段不能为空")

    gr = check_prompt_sync(task)
    if gr.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input blocked: {gr.message} (risk={gr.risk_level})",
        )

    conversation_id = body.get("conversation_id")
    context = {"conversation_id": conversation_id} if conversation_id else None
    user_id = current_user.user_id

    async def event_generator():
        executor = AgentExecutor()
        try:
            async for ev in executor.execute_stream(
                agent_id=agent_id, task=task, user_id=user_id, context=context):
                yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

Verify the imports `Depends`, `HTTPException`, `status`, `AuthenticatedUser`, `require_permission`, `Permission` are already present at the top of `agents.py` (the existing `execute_agent` uses all of them).

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_stream_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/agents.py tests/test_agent_stream_endpoint.py
git commit -m "feat(agents): add POST /agents/{id}/execute/stream SSE endpoint"
```

---

## Task 5: Frontend API client — `executeAgentStream`

**Files:**
- Modify: `webui/src/api/client.ts` (add next to `chatStream`, around line 161)

- [ ] **Step 1: Add the async generator method**

In `webui/src/api/client.ts`, add this method to the exported `api` object, directly after the `chatStream` method (it ends at line 161). It mirrors `chatStream`'s fetch + `ReadableStream` SSE parsing.

```typescript
  // Stream a single sub-agent run (SSE): start / tool_call_start / tool_call_end / text / done / error
  executeAgentStream: async function* (
    agentId: string | number,
    task: string,
    conversationId?: number,
  ) {
    const token = localStorage.getItem('token')
    const res = await fetch(`${BASE}/agents/${agentId}/execute/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ task, conversation_id: conversationId }),
    })
    if (!res.ok) throw new Error(await res.text())
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()!
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { yield JSON.parse(line.slice(6)) } catch { /* skip malformed */ }
        }
      }
    }
  },
```

- [ ] **Step 2: Type-check**

Run: `cd webui && npm run build` (or the project's typecheck script, e.g. `npx tsc --noEmit`)
Expected: 0 TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add webui/src/api/client.ts
git commit -m "feat(webui): add executeAgentStream SSE client"
```

---

## Task 6: Frontend — Agents-page run/test panel

**Files:**
- Modify: `webui/src/pages/Agents.tsx`

This adds a "运行" button per agent card and a modal panel that streams the run. Keep styling consistent with the existing modals in the file (the Form Modal at line 753 and the kind picker are good style references — reuse their overlay/card inline-style approach).

- [ ] **Step 1: Add a self-contained `AgentRunPanel` component**

Add this component near the other helper components in `Agents.tsx` (e.g. after `CodeBlock`/`PoolPicker`, before `export default function Agents()` at line 330). Import `api` is already imported in this file; confirm and reuse the existing import.

```tsx
type RunEvent =
  | { type: 'start'; agent_name?: string }
  | { type: 'tool_call_start'; name: string; arguments?: string; call_id: string }
  | { type: 'tool_call_end'; name: string; call_id: string; result_preview?: string; error?: boolean }
  | { type: 'text'; content: string }
  | { type: 'done'; output?: string; execution_time?: number }
  | { type: 'error'; content: string }

function AgentRunPanel({ agentId, agentName, onClose }: {
  agentId: string | number; agentName: string; onClose: () => void
}) {
  const [task, setTask] = useState('')
  const [running, setRunning] = useState(false)
  const [answer, setAnswer] = useState('')
  const [steps, setSteps] = useState<RunEvent[]>([])
  const [err, setErr] = useState<string | null>(null)

  const run = async () => {
    if (!task.trim() || running) return
    setRunning(true); setAnswer(''); setSteps([]); setErr(null)
    try {
      for await (const ev of api.executeAgentStream(agentId, task) as AsyncIterable<RunEvent>) {
        if (ev.type === 'text') setAnswer(a => a + ev.content)
        else if (ev.type === 'error') { setErr(ev.content); break }
        else if (ev.type === 'tool_call_start' || ev.type === 'tool_call_end') {
          setSteps(s => [...s, ev])
        }
      }
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 50 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 640, maxWidth: '92vw', maxHeight: '86vh',
        overflow: 'auto', background: 'var(--bg-card, #111)', border: '1px solid var(--border, #333)',
        borderRadius: 8, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <strong style={{ letterSpacing: '0.08em' }}>运行 · {agentName}</strong>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>✕</button>
        </div>

        <textarea value={task} onChange={e => setTask(e.target.value)} rows={3}
          placeholder="输入任务…" disabled={running}
          style={{ width: '100%', boxSizing: 'border-box', background: 'var(--bg, #0a0a0a)',
            color: 'var(--text)', border: '1px solid var(--border, #333)', borderRadius: 6, padding: 8 }} />

        <button onClick={run} disabled={running || !task.trim()}
          style={{ marginTop: 8, padding: '6px 16px', background: 'var(--accent)', color: '#000',
            border: 'none', borderRadius: 6, cursor: running ? 'default' : 'pointer', opacity: running ? 0.6 : 1 }}>
          {running ? '运行中…' : '运行'}
        </button>

        {steps.length > 0 && (
          <div style={{ marginTop: 14, fontSize: 13 }}>
            {steps.map((s, i) => s.type === 'tool_call_start' ? (
              <div key={`s${i}`} style={{ color: 'var(--text-muted)' }}>▸ 调用 {s.name}…</div>
            ) : s.type === 'tool_call_end' ? (
              <div key={`e${i}`} style={{ color: s.error ? '#f87171' : '#4ade80' }}>
                {s.error ? '✗' : '✓'} {s.name} — {s.result_preview}
              </div>
            ) : null)}
          </div>
        )}

        {answer && (
          <div style={{ marginTop: 14, whiteSpace: 'pre-wrap', lineHeight: 1.5,
            borderTop: '1px solid var(--border, #333)', paddingTop: 12 }}>{answer}</div>
        )}

        {err && <div style={{ marginTop: 12, color: '#f87171' }}>错误: {err}</div>}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire a "运行" button + panel state into the `Agents` component**

In `export default function Agents()`, add state near the other `useState` hooks (around line 346):

```tsx
  const [runningAgent, setRunningAgent] = useState<{ id: string | number; name: string } | null>(null)
```

In the agent card action row (where the existing `test`/`regenApiKey`/`openEdit`/`del` buttons are rendered, around lines 656–686), add a run button next to them. Use the agent object in scope there (`a`):

```tsx
                  <button onClick={() => setRunningAgent({ id: a.id!, name: a.agent_name })}
                    style={{ padding: 4, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none' }}>
                    运行
                  </button>
```

Then render the panel once, near the other modals at the end of the returned JSX (e.g. alongside the Form Modal):

```tsx
      {runningAgent && (
        <AgentRunPanel agentId={runningAgent.id} agentName={runningAgent.name}
          onClose={() => setRunningAgent(null)} />
      )}
```

- [ ] **Step 3: Type-check and build**

Run: `cd webui && npm run build`
Expected: 0 TypeScript errors. Adjust the `a.id` / `a.agent_name` field names if the local `Agent` type uses different property names (inspect the `Agent` type / how the existing `test(a.id!)` button reads fields).

- [ ] **Step 4: Manual smoke (optional but recommended)**

Bring up the stack (`docker compose up -d`), open the WebUI Agents page, click 运行 on an internal agent, enter a task, and confirm: tool steps appear as they happen and the answer streams in. For an external agent, confirm a single answer appears via the done fallback.

- [ ] **Step 5: Commit**

```bash
git add webui/src/pages/Agents.tsx
git commit -m "feat(webui): add streaming run/test panel to Agents page"
```

---

## Final verification

- [ ] Run the whole backend suite with the stack up:

```bash
docker compose up -d postgres redis
.venv/bin/python -m pytest -q
```

Expected: the previously-green 87 plus the new tests pass. (Without postgres/redis, the DB/Redis-backed tests error on connection — that is environmental, not a regression; see project status doc.)

- [ ] Frontend builds clean: `cd webui && npm run build` → 0 errors.

- [ ] Update `docs/superpowers/plans/project_status.md`: move "流式 sub-agent 输出" out of "Not yet implemented" and note the new endpoint + Agents run panel. Also correct the now-stale backlog lines discovered during planning (scheduled-task executor exists; chat file upload exists).

- [ ] Use `superpowers:finishing-a-development-branch` to decide merge/PR for `feat/streaming-internal-agent`.
