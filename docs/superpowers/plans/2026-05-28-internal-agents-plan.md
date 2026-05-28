# Internal (Configurable) Sub-Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second kind of sub-agent (`internal`) that is fully configurable inside CyberGuard — system prompt + LLM provider + selected skills (prompt content) + selected MCP tools (callable) + optional KB — and runs inline via an LLM tool-call loop. Existing remote sub-agents become `kind=external`. The Master Agent, Chat, and Group Chat treat both kinds equally.

**Architecture:** Single `agent_configs` table gains a `kind` column. New `InternalAgentRunner` runs a plain async tool-call loop against the LLM Router (no LangGraph). `AgentExecutor.execute()` gains one branch on `kind`. Memory persists per-agent as separate `conversations` rows tagged with `agent_id`, FK-linked to a parent conversation. MCP execution helpers are extracted into a reusable service so the runner can invoke MCP tools without round-tripping HTTP.

**Tech Stack:** FastAPI · SQLAlchemy 2 async · Alembic · openai SDK · pgvector · React + Vite + TS. Existing patterns: `app/services/*.py` (singletons), `app/routers/*.py` (thin), `app/models/*.py` (one model per file).

**Spec:** `docs/superpowers/specs/2026-05-28-internal-agents-design.md`

---

## Conventions for every task

- Test files live under `tests/`. Existing tests are smoke tests via HTTP (`tests/test_smoke_api.py`); add **unit tests** for the runner in new file `tests/test_internal_agent.py`. Add **smoke tests** for new HTTP shape in `tests/test_smoke_api.py`.
- Run tests with: `pytest tests/test_internal_agent.py -v` (unit) or `SMOKE_BASE_URL=http://localhost:8000 python -m unittest tests.test_smoke_api -v` (smoke — needs running stack).
- Apply migrations: `docker compose exec api alembic upgrade head`. Dev mode also auto-applies on api startup.
- After each task: `git add <files> && git commit -m "<msg>"`. Use existing commit-message style — short subject, optional body.

---

## Task 1: Migration 010 — agent kind + internal columns + conversation.agent_id

**Files:**
- Create: `alembic/versions/010_agent_kind_and_internal.py`

- [ ] **Step 1: Write the migration**

```python
"""agent kind and internal-agent columns

Revision ID: 010_agent_kind_and_internal
Revises: 009_req_typical_evidence
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa


revision = "010_agent_kind_and_internal"
down_revision = "009_req_typical_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # agent_configs
    op.add_column("agent_configs", sa.Column("kind", sa.String(20),
                                              nullable=False, server_default="external"))
    op.add_column("agent_configs", sa.Column("llm_provider_id", sa.Integer,
                                              sa.ForeignKey("providers.id", ondelete="SET NULL"),
                                              nullable=True))
    op.add_column("agent_configs", sa.Column("llm_model", sa.String(100), nullable=True))
    op.add_column("agent_configs", sa.Column("tool_loop_max_steps", sa.Integer,
                                              nullable=False, server_default="8"))
    op.add_column("agent_configs", sa.Column("memory_window", sa.Integer,
                                              nullable=False, server_default="20"))
    op.add_column("agent_configs", sa.Column("knowledge_base_id", sa.Integer,
                                              sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
                                              nullable=True))
    op.create_index("ix_agent_configs_kind", "agent_configs", ["kind"])
    # Backfill — every existing row was external by definition
    op.execute("UPDATE agent_configs SET kind='external'")

    # conversations — slice memory per internal agent + parent link
    op.add_column("conversations", sa.Column("agent_id", sa.Integer,
                                              sa.ForeignKey("agent_configs.id", ondelete="CASCADE"),
                                              nullable=True))
    op.add_column("conversations", sa.Column("parent_conversation_id", sa.Integer,
                                              sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                                              nullable=True))
    op.create_index("ix_conv_agent", "conversations", ["agent_id", "parent_conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_conv_agent", table_name="conversations")
    op.drop_column("conversations", "parent_conversation_id")
    op.drop_column("conversations", "agent_id")
    op.drop_index("ix_agent_configs_kind", table_name="agent_configs")
    op.drop_column("agent_configs", "knowledge_base_id")
    op.drop_column("agent_configs", "memory_window")
    op.drop_column("agent_configs", "tool_loop_max_steps")
    op.drop_column("agent_configs", "llm_model")
    op.drop_column("agent_configs", "llm_provider_id")
    op.drop_column("agent_configs", "kind")
```

- [ ] **Step 2: Apply and verify**

Run:
```
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```
Expected: `010_agent_kind_and_internal (head)`.

Then verify via psql:
```
docker compose exec postgres psql -U cyberguard -d cyberguard -c "\d agent_configs" | grep kind
docker compose exec postgres psql -U cyberguard -d cyberguard -c "SELECT id, kind FROM agent_configs LIMIT 5;"
```
Expected: `kind` column listed; every existing row has `kind='external'`.

- [ ] **Step 3: Commit**

```
git add alembic/versions/010_agent_kind_and_internal.py
git commit -m "feat(agents): migration 010 — agent kind + internal cols + conv.agent_id"
```

---

## Task 2: Update SQLAlchemy models

**Files:**
- Modify: `app/models/agent.py`
- Modify: `app/models/conversation.py`

- [ ] **Step 1: Edit `app/models/agent.py`** — add fields to `AgentConfig` after `metadata_json`:

```python
    # Kind discriminator: 'external' (HTTP / OpenClaw) or 'internal' (in-app)
    kind = Column(String(20), nullable=False, default="external", index=True)
    # Internal-agent only fields (nullable for external rows)
    llm_provider_id = Column(Integer, ForeignKey("providers.id", ondelete="SET NULL"), nullable=True)
    llm_model = Column(String(100), nullable=True)
    tool_loop_max_steps = Column(Integer, nullable=False, default=8)
    memory_window = Column(Integer, nullable=False, default=20)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True)
```

- [ ] **Step 2: Edit `app/models/conversation.py`** — add fields to `Conversation`:

```python
    # Internal-agent memory slice: when agent_id is set, this row stores the
    # message history for that internal agent under a parent (Master) conversation.
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True)
```

- [ ] **Step 3: Smoke-test imports**

Run:
```
docker compose exec api python -c "from app.models.agent import AgentConfig; from app.models.conversation import Conversation; print(AgentConfig.__table__.columns.keys()); print(Conversation.__table__.columns.keys())"
```
Expected: both lists contain the new columns; no SQLAlchemy errors.

- [ ] **Step 4: Commit**

```
git add app/models/agent.py app/models/conversation.py
git commit -m "feat(models): add kind/internal columns to AgentConfig and agent_id to Conversation"
```

---

## Task 3: Extract MCP execution helpers into a reusable service

**Files:**
- Create: `app/services/mcp_executor.py`
- Modify: `app/routers/mcp.py` (replace inline calls with service calls)

- [ ] **Step 1: Create `app/services/mcp_executor.py`** — move the two private helpers from the router verbatim, expose them publicly:

```python
"""MCP tool execution — reusable across the router and the internal-agent runner."""
from typing import Any, Dict
from app.models.mcp import MCPServer


# NOTE: copy _execute_stdio_tool and _execute_http_tool bodies VERBATIM from
# app/routers/mcp.py. Keep their signatures identical. After this task, the
# router will import from here instead of having its own private copies.
async def execute_stdio_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    # ... paste body of _execute_stdio_tool ...
    raise NotImplementedError("paste body from app/routers/mcp.py:_execute_stdio_tool")


async def execute_http_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    # ... paste body of _execute_http_tool ...
    raise NotImplementedError("paste body from app/routers/mcp.py:_execute_http_tool")


async def execute_mcp_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Transport-agnostic entry point. Dispatches by `server.transport_type`."""
    if server.transport_type == "stdio":
        return await execute_stdio_tool(server, tool_name, arguments)
    return await execute_http_tool(server, tool_name, arguments)
```

Implementation note: The literal bodies of `_execute_stdio_tool` and `_execute_http_tool` live in `app/routers/mcp.py`. Read them first (`grep -n "^async def _execute" app/routers/mcp.py` then `sed`-equivalent via the Read tool) and paste them in unmodified. Do NOT rewrite logic — this is a pure move.

- [ ] **Step 2: Modify `app/routers/mcp.py`** — at the import block add:

```python
from app.services.mcp_executor import execute_mcp_tool as _svc_execute_mcp_tool
```

Replace the dispatch inside `execute_mcp_tool` (router function) — find the block:
```python
        if server.transport_type == "stdio":
            result = await _execute_stdio_tool(server, tool.tool_name, body.arguments)
        else:
            result = await _execute_http_tool(server, tool.tool_name, body.arguments)
```

With:
```python
        result = await _svc_execute_mcp_tool(server, tool.tool_name, body.arguments)
```

Then DELETE the now-unused `_execute_stdio_tool` and `_execute_http_tool` private defs from the router file.

- [ ] **Step 3: Smoke-test the existing MCP execute endpoint**

Run an existing MCP tool via the REST endpoint (use any tool already configured in your dev DB):
```
curl -X POST http://localhost:8000/api/v1/mcp/tools/execute \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"tool_id": 1, "arguments": {}}'
```
Expected: same response shape as before the refactor (status `completed` or `failed` with `result`/`error`). If no MCP tools are configured, skip and rely on Task 4 unit tests for verification.

- [ ] **Step 4: Commit**

```
git add app/services/mcp_executor.py app/routers/mcp.py
git commit -m "refactor(mcp): extract execute_stdio/http_tool into mcp_executor service"
```

---

## Task 4: Extend LLM Router to support tool-calling

**Files:**
- Modify: `app/services/llm_router.py` — `chat()` at line ~623

- [ ] **Step 1: Write failing unit test**

Create `tests/test_llm_router_tools.py`:
```python
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("MOCK_MODE", "true")  # avoid real network

from app.services import llm_router as llm_router_module


@pytest.mark.asyncio
async def test_chat_returns_message_when_tools_passed(monkeypatch):
    router = llm_router_module.LLMRouter()

    # Fake AsyncOpenAI client whose chat.completions.create returns a message
    # with tool_calls set.
    fake_msg = MagicMock()
    fake_msg.content = None
    fake_msg.tool_calls = [MagicMock(id="call_1")]
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg, finish_reason="tool_calls")]
    fake_resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_should_strip_think", AsyncMock(return_value=False))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())

    # MOCK_MODE branch must be bypassed for this test
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    msg = await router.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "x"}}],
    )
    assert msg.tool_calls and msg.tool_calls[0].id == "call_1"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `pytest tests/test_llm_router_tools.py -v`
Expected: FAIL with `TypeError: chat() got an unexpected keyword argument 'tools'`.

- [ ] **Step 3: Implement `tools` kwarg**

In `app/services/llm_router.py` modify `chat()`:

```python
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """General chat completion.

        Returns:
            - str (final text) when `tools` is None — backward-compatible.
            - openai ChatCompletionMessage when `tools` is provided, so callers
              can inspect `.tool_calls`.
        """
        from app.core.telemetry import get_tracer
        tracer = get_tracer()

        active_model = model_override or model
        active_provider_id = provider_id
        if not active_model and provider_id:
            config = await self.get_provider_config_async(provider_id)
            if config and config.get("models"):
                active_model = config["models"][0]
        active_model = active_model or settings.MASTER_AGENT_MODEL

        master_config = await self._load_master_config()

        if settings.MOCK_MODE:
            last_msg = messages[-1]["content"] if messages else ""
            mock_text = f"🛡️ **CyberGuard (Mock Mode)**\n\n已收到您的消息：\"{last_msg[:100]}\"\n\n当前运行在 Mock 模式下，请配置真实的 AI Provider（Providers 页面）以获得实际的安全分析能力。"
            if tools is not None:
                # Return a stub message object compatible with .tool_calls / .content access
                from types import SimpleNamespace
                return SimpleNamespace(content=mock_text, tool_calls=None)
            return mock_text

        client = await self.get_client_async(provider_id=provider_id)

        with tracer.start_as_current_span(
            f"llm.chat/{active_model}",
            attributes={
                "llm.model": active_model,
                "llm.operation": "chat",
                "llm.num_messages": len(messages),
                "llm.has_tools": bool(tools),
            },
        ) as span:
            kwargs = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature_override if temperature_override is not None else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE),
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            raw_content = message.content or ""
            strip_think = await self._should_strip_think(provider_id)
            content = self._strip_think_blocks(raw_content) if strip_think else raw_content
            span.set_attribute("llm.response_length", len(content))
            span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)
            await self._record_token_usage(active_model, active_provider_id, response)

            if tools is not None:
                # Replace content with stripped version, return full message
                message.content = content
                return message
            return content
```

- [ ] **Step 4: Run test — verify it passes**

Run: `pytest tests/test_llm_router_tools.py -v`
Expected: PASS.

Also verify the no-tools path still works:
```
docker compose exec api python -c "
import asyncio
from app.services.llm_router import get_llm_router
print(asyncio.run(get_llm_router().chat([{'role':'user','content':'ping'}])))
"
```
Expected: a string (mock-mode response or a real provider reply), NOT a message object.

- [ ] **Step 5: Commit**

```
git add app/services/llm_router.py tests/test_llm_router_tools.py
git commit -m "feat(llm-router): accept tools kwarg, return ChatCompletionMessage when set"
```

---

## Task 5: InternalAgentRunner — skeleton + memory load/save

**Files:**
- Create: `app/services/internal_agent.py`
- Create: `tests/test_internal_agent.py`

- [ ] **Step 1: Write failing test for memory load/save round-trip**

Create `tests/test_internal_agent.py`:

```python
import json
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import get_db_context, AsyncSessionLocal
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
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/test_internal_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.internal_agent`.

- [ ] **Step 3: Implement skeleton with memory helpers**

Create `app/services/internal_agent.py`:

```python
"""Internal (in-app, configurable) sub-agent runner.

Runs an inline tool-call loop against the LLM Router. See:
  docs/superpowers/specs/2026-05-28-internal-agents-design.md
"""
import json
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation


class InternalAgentRunner:
    def __init__(self, config: Dict[str, Any]):
        self.agent_id: int = config["id"]
        self.agent_name: str = config["agent_name"]
        self.system_prompt: str = config.get("system_prompt") or ""
        self.llm_provider_id: Optional[int] = config.get("llm_provider_id")
        self.llm_model: Optional[str] = config.get("llm_model")
        self.max_steps: int = config.get("tool_loop_max_steps") or 8
        self.memory_window: int = config.get("memory_window") or 20
        self.knowledge_base_id: Optional[int] = config.get("knowledge_base_id")
        self.associated_skills: List[int] = config.get("associated_skills") or []
        meta = config.get("metadata_json") or {}
        self.mcp_tool_ids: List[int] = meta.get("mcp_tool_ids") or []
        self.permission_level: str = config.get("permission_level") or "medium"

    # -------- Memory --------

    async def _get_or_create_slice_row(
        self, session, parent_conversation_id: int, user_id: int
    ) -> Conversation:
        result = await session.execute(
            select(Conversation).where(
                Conversation.parent_conversation_id == parent_conversation_id,
                Conversation.agent_id == self.agent_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row
        row = Conversation(
            user_id=user_id,
            title=f"agent:{self.agent_name}",
            parent_conversation_id=parent_conversation_id,
            agent_id=self.agent_id,
            messages_json="[]",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def _load_memory(self, parent_conversation_id: Optional[int]) -> List[Dict[str, str]]:
        if parent_conversation_id is None:
            return []
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Conversation).where(
                    Conversation.parent_conversation_id == parent_conversation_id,
                    Conversation.agent_id == self.agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row or not row.messages_json:
                return []
            try:
                msgs = json.loads(row.messages_json) or []
            except json.JSONDecodeError:
                return []
            return msgs[-self.memory_window:]

    async def _append_memory(
        self, parent_conversation_id: Optional[int], user_id: int,
        messages: List[Dict[str, str]],
    ) -> None:
        if parent_conversation_id is None or not messages:
            return
        async with AsyncSessionLocal() as s:
            row = await self._get_or_create_slice_row(s, parent_conversation_id, user_id)
            existing = json.loads(row.messages_json or "[]")
            existing.extend(messages)
            row.messages_json = json.dumps(existing, ensure_ascii=False)
            await s.commit()

    # -------- Public entry point — implemented in Task 7 --------

    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int) -> Dict[str, Any]:
        raise NotImplementedError("implemented in Task 7")
```

- [ ] **Step 4: Run test — verify it passes**

Run: `pytest tests/test_internal_agent.py -v -k memory`
Expected: both memory tests PASS.

- [ ] **Step 5: Commit**

```
git add app/services/internal_agent.py tests/test_internal_agent.py
git commit -m "feat(agents): InternalAgentRunner skeleton + memory load/save"
```

---

## Task 6: InternalAgentRunner — tool catalog (MCP + KB) and prompt assembly

**Files:**
- Modify: `app/services/internal_agent.py`
- Modify: `tests/test_internal_agent.py` (add tests)

- [ ] **Step 1: Write failing test for prompt + tool catalog**

Append to `tests/test_internal_agent.py`:

```python
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
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/test_internal_agent.py -v -k "system_prompt or kb"`
Expected: FAIL with `AttributeError` for `_load_skill_bodies` / `_build_system_prompt` / `_build_tools`.

- [ ] **Step 3: Implement methods**

In `app/services/internal_agent.py` add these methods on `InternalAgentRunner` (before `execute`):

```python
    # -------- System prompt assembly --------

    async def _load_skill_bodies(self, skill_ids: List[int]) -> Dict[int, str]:
        if not skill_ids:
            return {}
        from app.models.skill import Skill
        async with AsyncSessionLocal() as s:
            result = await s.execute(select(Skill).where(Skill.id.in_(skill_ids),
                                                          Skill.is_active == True))
            rows = result.scalars().all()
        return {r.id: (r.md_content or "") for r in rows}

    async def _build_system_prompt(self) -> str:
        parts = [self.system_prompt] if self.system_prompt else []
        bodies = await self._load_skill_bodies(self.associated_skills)
        if bodies:
            parts.append("\n\n## Skills available to you\n")
            for sid in self.associated_skills:
                body = bodies.get(sid)
                if body:
                    parts.append(f"\n### Skill #{sid}\n{body}\n")
        return "\n".join(parts).strip() or "You are an assistant."

    # -------- Tool catalog --------

    async def _load_mcp_tools(self) -> List[Dict[str, Any]]:
        """Resolve mcp_tool_ids into OpenAI function-tool schemas."""
        if not self.mcp_tool_ids:
            return []
        from app.models.mcp import MCPTool
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(MCPTool).where(MCPTool.id.in_(self.mcp_tool_ids),
                                       MCPTool.is_active == True)
            )
            tools = result.scalars().all()
        out = []
        for t in tools:
            try:
                schema = json.loads(t.input_schema_json) if t.input_schema_json else {}
            except json.JSONDecodeError:
                schema = {}
            out.append({
                "type": "function",
                "function": {
                    "name": t.tool_name,
                    "description": t.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            })
        return out

    async def _build_tools(self) -> List[Dict[str, Any]]:
        tools = await self._load_mcp_tools()
        if self.knowledge_base_id:
            tools.append({
                "type": "function",
                "function": {
                    "name": "kb_search",
                    "description": "Search the agent's attached knowledge base.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "search query"},
                            "top_k": {"type": "integer", "default": 5,
                                       "description": "max number of chunks to return"},
                        },
                        "required": ["query"],
                    },
                },
            })
        return tools
```

- [ ] **Step 4: Run — verify it passes**

Run: `pytest tests/test_internal_agent.py -v -k "system_prompt or kb"`
Expected: both PASS.

- [ ] **Step 5: Commit**

```
git add app/services/internal_agent.py tests/test_internal_agent.py
git commit -m "feat(agents): InternalAgentRunner — skill prompt assembly + tool catalog"
```

---

## Task 7: InternalAgentRunner — tool dispatch + execute() loop

**Files:**
- Modify: `app/services/internal_agent.py`
- Modify: `tests/test_internal_agent.py` (add tests)

- [ ] **Step 1: Write failing test for dispatch + execute loop**

Append to `tests/test_internal_agent.py`:

```python
@pytest.mark.asyncio
async def test_dispatch_kb_search(monkeypatch):
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
```

- [ ] **Step 2: Run — verify all three fail**

Run: `pytest tests/test_internal_agent.py -v -k "dispatch or high_permission or loop_terminates"`
Expected: FAIL — `_dispatch` / `execute` not implemented (latter raises NotImplementedError).

- [ ] **Step 3: Implement dispatch + execute()**

In `app/services/internal_agent.py`, add a module-level import block at the top:

```python
from app.services.knowledge_service import KnowledgeService

knowledge_service = KnowledgeService()  # singleton; mockable from tests
```

(If `KnowledgeService.search(kb_id, query, top_k)` does not exist with that exact signature, check `app/services/knowledge_service.py` and adapt the call inside `_dispatch`. The plan author verified `knowledge_service.py` is the right module — exact API is implementation-time detail.)

Then add these methods on `InternalAgentRunner` (replace the `NotImplementedError` `execute`):

```python
    async def _dispatch(self, call) -> str:
        """Execute a single tool_call and return a JSON-safe string result."""
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}

        # 1. MCP tool lookup
        if hasattr(self, "_mcp_by_name") and name in self._mcp_by_name:
            from app.services.mcp_executor import execute_mcp_tool
            tool_row, server_row = self._mcp_by_name[name]
            try:
                result = await execute_mcp_tool(server_row, tool_row.tool_name, args)
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception as e:
                return f"ERROR: MCP tool {name!r} failed: {e}"

        # 2. KB synthetic tool
        if name == "kb_search" and self.knowledge_base_id:
            try:
                chunks = await knowledge_service.search(
                    self.knowledge_base_id,
                    args.get("query", ""),
                    args.get("top_k", 5),
                )
                return json.dumps(chunks, ensure_ascii=False, default=str)
            except Exception as e:
                return f"ERROR: kb_search failed: {e}"

        return f"ERROR: unknown tool {name!r}"

    async def _resolve_mcp_lookup(self) -> None:
        """Populate self._mcp_by_name = {tool_name: (MCPTool, MCPServer)} for dispatch."""
        self._mcp_by_name = {}
        if not self.mcp_tool_ids:
            return
        from app.models.mcp import MCPTool, MCPServer
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(MCPTool, MCPServer)
                .join(MCPServer, MCPServer.id == MCPTool.server_id)
                .where(MCPTool.id.in_(self.mcp_tool_ids), MCPTool.is_active == True)
            )
            for tool, server in result.all():
                self._mcp_by_name[tool.tool_name] = (tool, server)

    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int) -> Dict[str, Any]:
        """Run the tool-call loop. Returns same shape as SubAgentWrapper.execute()."""
        from app.services.llm_router import get_llm_router

        start = time.monotonic()

        # 1. Permission gate
        if self.permission_level == "high":
            return {
                "status": "needs_approval",
                "output": None,
                "error": "High permission internal agent requires approval",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": 0,
            }

        # 2. Build system prompt + tool catalog + memory
        system_prompt = await self._build_system_prompt()
        tools = await self._build_tools()
        await self._resolve_mcp_lookup()
        history = await self._load_memory(conversation_id)

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": task})

        # Track new messages added this turn (for persistence)
        new_messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
        tool_call_log: List[Dict[str, Any]] = []

        router = get_llm_router()
        final_text: Optional[str] = None

        for step in range(self.max_steps):
            try:
                msg = await router.chat(
                    messages=messages,
                    provider_id=self.llm_provider_id,
                    model=self.llm_model,
                    tools=tools if tools else None,
                )
            except Exception as e:
                return {
                    "status": "failed",
                    "output": None,
                    "error": f"LLM error at step {step}: {e}",
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "execution_time": round(time.monotonic() - start, 2),
                }

            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                final_text = getattr(msg, "content", None) or ""
                new_messages.append({"role": "assistant", "content": final_text})
                break

            # Append assistant message that requested tools
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

            for call in tool_calls:
                result_str = await self._dispatch(call)
                tool_call_log.append({"name": call.function.name,
                                       "arguments": call.function.arguments,
                                       "result_preview": result_str[:200]})
                tool_msg = {"role": "tool", "tool_call_id": call.id,
                            "content": result_str}
                messages.append(tool_msg)
                new_messages.append(tool_msg)

        if final_text is None:
            return {
                "status": "error",
                "output": None,
                "error": f"exceeded tool_loop_max_steps ({self.max_steps})",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": round(time.monotonic() - start, 2),
                "tool_calls": tool_call_log,
            }

        # Persist memory slice
        await self._append_memory(conversation_id, user_id, new_messages)

        return {
            "status": "completed",
            "output": final_text,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "execution_time": round(time.monotonic() - start, 2),
            "tool_calls": tool_call_log,
        }
```

- [ ] **Step 4: Run — verify all three new tests pass**

Run: `pytest tests/test_internal_agent.py -v`
Expected: all tests PASS (the four prior tests still pass too).

- [ ] **Step 5: Commit**

```
git add app/services/internal_agent.py tests/test_internal_agent.py
git commit -m "feat(agents): InternalAgentRunner — dispatch + execute tool-call loop"
```

---

## Task 8: Wire InternalAgentRunner into AgentExecutor

**Files:**
- Modify: `app/services/agent_executor.py`
- Modify: `tests/test_internal_agent.py` (add integration test)

- [ ] **Step 1: Write failing test — AgentExecutor routes by kind**

Append to `tests/test_internal_agent.py`:

```python
@pytest.mark.asyncio
async def test_agent_executor_routes_internal_kind(monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.core.database import AsyncSessionLocal
    from app.models.agent import AgentConfig

    async with AsyncSessionLocal() as s:
        ag = AgentConfig(agent_name="exec_test_int", kind="internal",
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
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/test_internal_agent.py::test_agent_executor_routes_internal_kind -v`
Expected: FAIL with `TypeError: execute() got an unexpected keyword argument 'context'` (or the kind branch is missing).

- [ ] **Step 3: Modify `AgentExecutor.execute()` in `app/services/agent_executor.py`**

Change the signature at line 286:
```python
    async def execute(
        self,
        agent_id: int,
        task: str,
        user_id: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
```

In the `config_dict = {...}` block (line 324), add the internal-agent fields:
```python
            config_dict = {
                "id": agent_obj.id,
                "agent_name": agent_obj.agent_name,
                "backend_type": agent_obj.backend_type,
                "kind": agent_obj.kind,
                "provider_id": agent_obj.provider_id,
                "llm_provider_id": agent_obj.llm_provider_id,
                "llm_model": agent_obj.llm_model,
                "tool_loop_max_steps": agent_obj.tool_loop_max_steps,
                "memory_window": agent_obj.memory_window,
                "knowledge_base_id": agent_obj.knowledge_base_id,
                "endpoint_url": agent_obj.endpoint_url,
                "env_vars_encrypted": agent_obj.env_vars_encrypted,
                "system_prompt": agent_obj.system_prompt,
                "permission_level": getattr(agent_obj, "permission_level", "medium"),
                "associated_skills": agent_obj.associated_skills,
                "metadata_json": agent_obj.metadata_json,
                "api_key": getattr(agent_obj, "api_key", "") or "",
                "auth_mode": getattr(agent_obj, "auth_mode", "api_key"),
                "streaming": getattr(agent_obj, "streaming", True),
            }
```

Replace the dispatch block (around line 350):
```python
        # Check permission level (external — internal handles it internally)
        permission_level = config_dict.get("permission_level", "medium")
        kind = config_dict.get("kind") or "external"

        if kind == "internal":
            from app.services.internal_agent import InternalAgentRunner
            runner = InternalAgentRunner(config_dict)
            conv_id = (context or {}).get("conversation_id")
            result = await runner.execute(task=task, conversation_id=conv_id, user_id=user_id)
        else:
            if permission_level == "high":
                return {
                    "status": "needs_approval",
                    "output": None,
                    "error": "High permission agent requires approval",
                }
            backend = config_dict["backend_type"]
            if backend == "openclaw":
                result = await self._execute_openclaw(config_dict, task)
            else:
                wrapper = SubAgentWrapper(config_dict)
                result = await wrapper.execute(task=task, context={"user_id": user_id})

        result["agent_id"] = agent_id
        result["agent_name"] = config_dict.get("agent_name")
        result["timestamp"] = datetime.utcnow().isoformat()
        return result
```

Also extend `execute_parallel` (line 456):
```python
    async def execute_parallel(self, agent_ids: list, task: str, user_id: int,
                                context: Optional[Dict[str, Any]] = None) -> Dict[int, Dict[str, Any]]:
        import asyncio
        tasks = [self.execute(agent_id, task, user_id, context=context)
                 for agent_id in agent_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            agent_id: results[i] if not isinstance(results[i], Exception) else {
                "status": "error", "error": str(results[i]),
            }
            for i, agent_id in enumerate(agent_ids)
        }
```

- [ ] **Step 4: Run — verify it passes**

Run: `pytest tests/test_internal_agent.py::test_agent_executor_routes_internal_kind -v`
Expected: PASS. Also re-run full file: `pytest tests/test_internal_agent.py -v` — all PASS.

- [ ] **Step 5: Commit**

```
git add app/services/agent_executor.py tests/test_internal_agent.py
git commit -m "feat(executor): route kind=internal to InternalAgentRunner; thread context"
```

---

## Task 9: Thread `conversation_id` through Master Agent and Group Chat

**Files:**
- Modify: `app/agents/master.py`
- Modify: `app/services/group_chat.py`

- [ ] **Step 1: Update master.py call sites**

Search `master.py` for every `executor.execute(` and `AgentExecutor().execute(` and `execute_parallel(`. For each call site that has access to `state` (the LangGraph state), pass:
```python
context={"conversation_id": getattr(state, "conversation_id", None)}
```

Use grep:
```
grep -n "execute(\|execute_parallel(" app/agents/master.py
```

For each occurrence, append `context={...}` as shown above. Where the state object doesn't carry conversation_id, leave `context=None` (the executor defaults handle it).

- [ ] **Step 2: Update GroupChatService**

Edit `app/services/group_chat.py`:

In `GroupChatSession` dataclass (line ~23) add:
```python
    parent_conversation_id: Optional[int] = None
```

In `create_session` (line ~46) add parameter:
```python
    async def create_session(
        self,
        user_id: int,
        agent_ids: List[int],
        initial_message: str,
        max_rounds: int = 5,
        parent_conversation_id: Optional[int] = None,
    ) -> str:
```

And inside, propagate:
```python
        session = GroupChatSession(
            session_id=session_id,
            user_id=user_id,
            agent_ids=agent_ids,
            max_rounds=max_rounds,
            parent_conversation_id=parent_conversation_id,
        )
```

In every place that calls `self.executor.execute(agent_id, ..., user_id)` add:
```python
        context={"conversation_id": session.parent_conversation_id}
```

Use grep to find all call sites:
```
grep -n "self.executor.execute\|executor.execute_parallel" app/services/group_chat.py
```

Update each accordingly.

- [ ] **Step 3: Smoke check — imports still resolve**

Run:
```
docker compose exec api python -c "from app.agents.master import *; from app.services.group_chat import GroupChatService; print('ok')"
```
Expected: `ok` (no import errors).

- [ ] **Step 4: Re-run unit tests**

Run: `pytest tests/test_internal_agent.py -v`
Expected: all PASS (no regression).

- [ ] **Step 5: Commit**

```
git add app/agents/master.py app/services/group_chat.py
git commit -m "feat(master,groupchat): thread conversation_id as context to AgentExecutor"
```

---

## Task 10: Pydantic schemas + agent CRUD validation

**Files:**
- Modify: `app/schemas/agent.py` (or whichever file holds agent Pydantic models — find with `grep -rln "class AgentConfigCreate\|AgentCreate\|AgentRead" app/`)
- Modify: `app/routers/agents.py`

- [ ] **Step 1: Find existing agent schemas**

Run:
```
grep -rln "class AgentConfig\|AgentCreate\|AgentRead\|AgentUpdate" app/
```

Open the file(s) returned.

- [ ] **Step 2: Extend `AgentCreate` / `AgentUpdate` / `AgentRead` with new fields**

Add to the Pydantic models (mirrors model columns added in Task 2):
```python
    kind: Optional[str] = "external"  # "external" | "internal"
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    tool_loop_max_steps: int = 8
    memory_window: int = 20
    knowledge_base_id: Optional[int] = None
```

For `AgentRead`, include the same fields (read-side).

- [ ] **Step 3: Add validation in the agent create/update router**

In `app/routers/agents.py` find the POST / PUT handlers. Before persisting, validate by kind:

```python
def _validate_agent_payload(body) -> None:
    kind = (body.kind or "external").lower()
    if kind not in ("external", "internal"):
        raise HTTPException(400, f"invalid kind: {body.kind!r}")
    if kind == "external":
        if not body.backend_type:
            raise HTTPException(400, "external agent requires backend_type")
        if body.backend_type in ("hermes", "custom") and not body.endpoint_url:
            raise HTTPException(400, f"{body.backend_type} requires endpoint_url")
    else:  # internal
        if not body.llm_provider_id:
            raise HTTPException(400, "internal agent requires llm_provider_id")
        if body.endpoint_url:
            raise HTTPException(400, "internal agent must not set endpoint_url")
        if body.backend_type:
            raise HTTPException(400, "internal agent must not set backend_type")
```

Call `_validate_agent_payload(body)` at the top of the create and update handlers.

- [ ] **Step 4: Smoke-test via curl**

Create one of each kind:
```
TOKEN=...  # admin JWT
# Internal:
curl -X POST http://localhost:8000/api/v1/agents -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"smoke_int","kind":"internal","llm_provider_id":1,"system_prompt":"hi"}'
# Expect 200 / 201 with kind=internal in the response.

# Invalid internal (missing provider):
curl -i -X POST http://localhost:8000/api/v1/agents -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"bad_int","kind":"internal"}'
# Expect HTTP 400 with "internal agent requires llm_provider_id".
```

- [ ] **Step 5: Commit**

```
git add app/schemas/agent.py app/routers/agents.py
git commit -m "feat(agents): kind-aware Pydantic schemas + CRUD validation"
```

---

## Task 11: WebUI — kind column, filter, chooser modal, internal-agent form

**Files:**
- Modify: `webui/src/api/agents.ts` (types)
- Modify: `webui/src/pages/Agents.tsx` (or the actual file — find with `grep -rln "agent_configs\|/api/v1/agents" webui/src/`)
- Possibly create: new internal-agent form component

- [ ] **Step 1: Update TypeScript types in `webui/src/api/agents.ts`**

Add fields to the existing `Agent` / `AgentCreate` / `AgentUpdate` interfaces (mirror Task 10):
```ts
  kind?: "external" | "internal";
  llm_provider_id?: number | null;
  llm_model?: string | null;
  tool_loop_max_steps?: number;
  memory_window?: number;
  knowledge_base_id?: number | null;
```

- [ ] **Step 2: Add Kind column + filter to Agents page**

In the agents-list table, add a column rendering `agent.kind` as a coloured badge:
- `internal` → blue/green
- `external` → existing colour scheme

Add a `<select>` filter above the table: All / External / Internal. Filter the list client-side or pass `?kind=` to the list endpoint if backend filtering is desired (out of scope; client-side is fine for v1).

- [ ] **Step 3: Replace "New Agent" button with a kind-chooser**

The current single "New Agent" button opens the external-agent form. Wrap it in a modal whose first step asks "External (HTTP / OpenClaw) or Internal (configured in-app)?" and routes to the appropriate form on selection.

Build the **internal-agent form**: fields = name, description, system_prompt (textarea), llm_provider (dropdown of active providers via existing `/api/v1/providers`), llm_model (text input with placeholder "auto"), knowledge_base (dropdown via existing `/api/v1/knowledge-bases`), tool_loop_max_steps (number, default 8), memory_window (number, default 20), permission_level (low/medium/high), associated_skills (multi-select pulled from existing skill API), mcp_tool_ids (multi-select pulled from `/api/v1/mcp/tools/all`). On submit, POST to `/api/v1/agents` with `kind=internal`.

- [ ] **Step 4: Make group-chat agent-picker show both kinds**

Find the group-chat agent multi-select (`grep -rln "agent_ids" webui/src/`). Ensure each option in the picker shows its kind badge (so users know what they're including in a group). No filtering needed — both kinds are valid participants.

- [ ] **Step 5: Manual UI smoke**

Start the WebUI (`cd webui && npm run dev` or rely on the docker `webui` service). In a browser:
1. Open the Agents page — verify Kind column appears, existing rows show `external`.
2. Click New Agent → choose Internal → fill the form → submit → row appears with `kind=internal`.
3. Open the form again → choose External → fill it → existing flow still works.
4. Open Group Chat → pick the new internal agent + an existing external agent → send a message → both reply.

This is a manual test — note the result in the commit message.

- [ ] **Step 6: Commit**

```
git add webui/src/api/agents.ts webui/src/pages/Agents.tsx <any-new-form-file>
git commit -m "feat(webui): kind column + chooser + internal-agent form on Agents page

Manual smoke: external + internal agents both visible with kind badge;
internal form creates kind=internal row; group chat dispatches to both."
```

---

## Task 12: Optional seed — example internal agents (gated by env flag)

**Files:**
- Modify: wherever startup seeding lives — find with `grep -rln "seed_default\|preset_providers\|seed_iso27001" app/`

- [ ] **Step 1: Identify the existing seed entrypoint**

Run:
```
grep -rln "def seed\|_seed_" app/
```
Open the relevant file. Existing patterns: idempotent on every startup.

- [ ] **Step 2: Add `seed_example_internal_agents()`**

In the same file (or `app/services/agent_seed.py` if a new file fits the existing convention better):

```python
import os
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig


SEED_FLAG = "SEED_EXAMPLE_INTERNAL_AGENTS"


async def seed_example_internal_agents() -> None:
    """Idempotent — runs on startup only when SEED_EXAMPLE_INTERNAL_AGENTS=true."""
    if os.getenv(SEED_FLAG, "false").lower() != "true":
        return

    examples = [
        {
            "agent_name": "triage_analyst",
            "kind": "internal",
            "description": "SOC triage assistant — classifies and prioritises incoming alerts.",
            "system_prompt": ("You are a Tier-1 SOC analyst. Classify the alert, suggest "
                              "next steps, and cite any IOCs."),
            "is_active": True,
            "permission_level": "medium",
            "tool_loop_max_steps": 6,
            "memory_window": 20,
        },
        {
            "agent_name": "policy_writer",
            "kind": "internal",
            "description": "Governance copilot — drafts policy text grounded in attached KB.",
            "system_prompt": ("You draft governance / policy text in the bank's house style. "
                              "Cite the KB. Be concise."),
            "is_active": True,
            "permission_level": "medium",
            "tool_loop_max_steps": 4,
            "memory_window": 30,
        },
    ]

    async with AsyncSessionLocal() as s:
        for ex in examples:
            existing = await s.execute(
                select(AgentConfig).where(AgentConfig.agent_name == ex["agent_name"])
            )
            if existing.scalar_one_or_none():
                continue
            s.add(AgentConfig(**ex))
        await s.commit()
```

Then register the call in the existing startup-seed hook (alongside `seed_iso27001_framework`, `seed_default_prompts`, etc. — find the call site in `app/main.py` or `app/core/startup.py`).

- [ ] **Step 3: Smoke check**

Set the flag and restart:
```
docker compose exec -e SEED_EXAMPLE_INTERNAL_AGENTS=true api python -c "
import asyncio
from <module> import seed_example_internal_agents
asyncio.run(seed_example_internal_agents())
"
docker compose exec postgres psql -U cyberguard -d cyberguard -c \
  "SELECT agent_name, kind FROM agent_configs WHERE kind='internal';"
```
Expected: `triage_analyst` and `policy_writer` rows present.

- [ ] **Step 4: Commit**

```
git add <files>
git commit -m "feat(agents): optional seed of example internal agents (env-gated)"
```

---

## Task 13: End-to-end smoke test

**Files:**
- Modify: `tests/test_smoke_api.py`

- [ ] **Step 1: Add a smoke test for internal-agent CRUD + execute**

Append a method to the `TestAPISmoke` class:

```python
    def test_internal_agent_lifecycle(self):
        token = self._login()

        # List providers — pick the first active one
        status, providers = _request("GET", "/providers", token=token)
        self.assertEqual(status, 200)
        active = [p for p in providers.get("providers", providers) if p.get("is_active")]
        if not active:
            self.skipTest("no active providers configured")
        provider_id = active[0]["id"]

        # Create internal agent
        name = f"smoke_int_{uuid.uuid4().hex[:6]}"
        body = {"agent_name": name, "kind": "internal", "llm_provider_id": provider_id,
                "system_prompt": "You reply with 'pong'.", "permission_level": "medium",
                "tool_loop_max_steps": 2, "memory_window": 0}
        status, created = _request("POST", "/agents", body=body, token=token)
        self.assertEqual(status, 201, msg=created)
        agent_id = created["id"]
        self.assertEqual(created["kind"], "internal")

        try:
            # Invoke via chat with explicit agent_id
            status, chat_resp = _request(
                "POST", "/chat",
                body={"message": "ping", "agent_id": agent_id, "mode": "normal"},
                token=token,
            )
            self.assertEqual(status, 200, msg=chat_resp)
            # Either the assistant replies directly or we get a structured reply.
            # The contract is just that it didn't 500.
        finally:
            _request("DELETE", f"/agents/{agent_id}", token=token)
```

The above assumes a `_login` helper. If the existing class has a different login pattern, copy it from a sibling test method.

- [ ] **Step 2: Run smoke against the stack**

```
docker compose up -d
SMOKE_BASE_URL=http://localhost:8000 python -m unittest tests.test_smoke_api.TestAPISmoke.test_internal_agent_lifecycle -v
```
Expected: PASS (or skip if no active provider — that's acceptable in a fresh dev env).

- [ ] **Step 3: Commit**

```
git add tests/test_smoke_api.py
git commit -m "test(smoke): internal-agent lifecycle — create, invoke via chat, delete"
```

---

## Task 14: Memory note + doc sync

**Files:**
- Modify: project memory at `/Users/jc/.claude/projects/-Users-jc-Documents-cyber-agent-cyberguard/memory/project_status.md`
- Possibly modify: any high-level architecture doc in `docs/` that mentions sub-agents

- [ ] **Step 1: Update project memory with the new module**

Add to the "Extra features beyond the original design" cumulative list:
```
- **(2026-05-28)** Internal (configurable) sub-agents: `kind=internal` in `agent_configs`, runs inline via new `InternalAgentRunner` tool-call loop (no LangGraph); external (OpenClaw/Hermes/Custom) agents auto-labelled `kind=external` by migration 010; both kinds equal participants in Master, Chat, Group Chat; per-agent memory persists in `conversations` rows tagged with `agent_id` + `parent_conversation_id`; MCP execution helpers extracted into `app/services/mcp_executor.py`.
```

And update DB state:
```
- Current Alembic head: `010_agent_kind_and_internal`
```

- [ ] **Step 2: Check for stale architecture docs**

Run:
```
grep -rln "sub-agent\|sub agent\|backend_type" docs/
```

If any high-level doc still says "Sub-agents are always remote HTTP", update it to mention the two kinds. Keep edits minimal — most narrative docs probably don't need touching.

- [ ] **Step 3: Commit**

```
git add /Users/jc/.claude/projects/-Users-jc-Documents-cyber-agent-cyberguard/memory/project_status.md docs/
git commit -m "docs: sync project memory + arch notes for internal sub-agents"
```

(If the memory file lives outside the repo, skip it from the git add — just save the file.)

---

## Done

After Task 14:
- All sub-agents are kinded; existing rows are `external`, new rows can be `internal`.
- Master Agent, Chat (NL + explicit), Group Chat, and expert-mode fan-out treat both kinds equally.
- Internal agents have their own memory slice keyed on `(parent_conversation_id, agent_id)`.
- Skill pool feeds the system prompt; MCP pool feeds the callable tool list; KB optionally adds `kb_search`. All three are per-agent subsets.
- WebUI distinguishes kinds via a badge and offers a chooser when creating.

## Out of scope (do not implement here)

- Streaming output for internal agents.
- Long-term memory beyond the conversation slice.
- Internal agents calling other internal agents as tools.
- Per-tool RBAC for the synthetic `kb_search` tool (uses agent-level `permission_level` only).
- Per-call provider override on a single internal agent.
