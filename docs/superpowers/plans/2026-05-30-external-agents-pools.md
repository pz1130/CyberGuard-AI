# External Agents Using Pools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver assigned Skills/Tools/MCP context to external agents (all backends) via a `/gateway/manifest` endpoint authenticated with per-agent API keys.

**Architecture:** All `AgentConfig` rows get a CyberGuard API key on creation; a new `GET /gateway/manifest` endpoint returns the assigned pool content for the calling agent; OpenClaw poll responses gain a `has_manifest` hint; Custom/Hermes payloads gain a `manifest_url` field; `get_mcp_tools_for_agent` is refactored to read the `associated_mcp_tools` column first.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest + pytest-asyncio + unittest.mock

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/config.py` | Modify | Add `BASE_URL: str = ""` setting |
| `app/schemas/gateway.py` | Create | Pydantic schemas for manifest response |
| `app/routers/gateway.py` | Modify | Add `GET /gateway/manifest`; add `has_manifest` to poll |
| `app/routers/agents.py` | Modify | Remove `backend_type == "openclaw"` gate on key generation |
| `app/services/agent_executor.py` | Modify | Inject `manifest_url` in `SubAgentWrapper.execute`; refactor `get_mcp_tools_for_agent` |
| `tests/test_gateway_manifest.py` | Create | Unit tests for manifest endpoint and related changes |

---

## Task 1: Add `BASE_URL` to config and create gateway schemas

**Files:**
- Modify: `app/config.py`
- Create: `app/schemas/gateway.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_gateway_manifest.py`:

```python
"""Tests for GET /gateway/manifest and related changes."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Task 1 — Schema smoke
# ---------------------------------------------------------------------------

def test_manifest_schemas_round_trip():
    from app.schemas.gateway import (
        ManifestSkill, ManifestTool, ManifestMCPTool, ManifestResponse,
    )
    skill = ManifestSkill(id=1, name="port-scan", description="desc", md_content="# MD")
    tool = ManifestTool(
        id=2, name="nmap", description="net mapper",
        command_template="nmap {target}", input_schema={"type": "object"},
    )
    mcp = ManifestMCPTool(id=3, name="search_cve", description=None, input_schema={})
    resp = ManifestResponse(
        agent_id=7, agent_name="ScanBot",
        skills=[skill], tools=[tool], mcp_tools=[mcp],
    )
    data = resp.model_dump()
    assert data["agent_id"] == 7
    assert data["skills"][0]["md_content"] == "# MD"
    assert data["tools"][0]["command_template"] == "nmap {target}"
    assert data["mcp_tools"][0]["name"] == "search_cve"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
pytest tests/test_gateway_manifest.py::test_manifest_schemas_round_trip -v
```

Expected: `ModuleNotFoundError: No module named 'app.schemas.gateway'`

- [ ] **Step 3: Add `BASE_URL` to `app/config.py`**

In `app/config.py`, add after `SUB_AGENT_MAX_RETRIES`:

```python
    # Public base URL used to inject manifest_url into external agent payloads.
    # Leave empty to disable manifest_url injection (safe default).
    BASE_URL: str = ""
```

- [ ] **Step 4: Create `app/schemas/gateway.py`**

```python
"""Pydantic schemas for the /gateway/manifest endpoint."""
from typing import Optional
from pydantic import BaseModel


class ManifestSkill(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    md_content: str


class ManifestTool(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    command_template: Optional[str] = None
    input_schema: dict


class ManifestMCPTool(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    input_schema: dict


class ManifestResponse(BaseModel):
    agent_id: int
    agent_name: str
    skills: list[ManifestSkill]
    tools: list[ManifestTool]
    mcp_tools: list[ManifestMCPTool]
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/test_gateway_manifest.py::test_manifest_schemas_round_trip -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/schemas/gateway.py tests/test_gateway_manifest.py
git commit -m "feat: add BASE_URL config and gateway manifest schemas"
```

---

## Task 2: `GET /gateway/manifest` endpoint

**Files:**
- Modify: `app/routers/gateway.py`
- Modify: `tests/test_gateway_manifest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gateway_manifest.py`:

```python
# ---------------------------------------------------------------------------
# Task 2 — GET /gateway/manifest
# ---------------------------------------------------------------------------

def _fake_agent(skills=None, tools=None, mcp=None):
    return SimpleNamespace(
        id=7, agent_name="ScanBot",
        associated_skills=skills,
        associated_tools=tools,
        associated_mcp_tools=mcp,
    )


def _mock_session_ctx(rows=None):
    """Return a mock async context manager whose session.execute returns rows."""
    rows = rows or []
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=mock_result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_manifest_empty_pools():
    """Agent with no assignments returns three empty arrays."""
    from app.routers import gateway as gw

    with patch.object(gw, "_auth_agent", AsyncMock(return_value=_fake_agent())):
        with patch("app.routers.gateway.AsyncSessionLocal", return_value=_mock_session_ctx()):
            result = await gw.manifest(x_api_key="oc-test")

    assert result.agent_id == 7
    assert result.agent_name == "ScanBot"
    assert result.skills == []
    assert result.tools == []
    assert result.mcp_tools == []


@pytest.mark.asyncio
async def test_manifest_returns_assigned_skill():
    """Agent with one skill gets it back in full."""
    from app.routers import gateway as gw

    fake_skill = SimpleNamespace(
        id=3, name="port-scan", description="Port scanning runbook",
        md_content="# Port Scan\nRun nmap...",
    )

    agent = _fake_agent(skills=[3])

    with patch.object(gw, "_auth_agent", AsyncMock(return_value=agent)):
        # Session is called three times (skills, tools, mcp_tools).
        # Only skills query needs a real row; the others return empty.
        mock_session = AsyncMock()
        call_count = {"n": 0}

        async def fake_execute(_q):
            result = MagicMock()
            # First call is skills query
            if call_count["n"] == 0:
                result.scalars.return_value.all.return_value = [fake_skill]
            else:
                result.scalars.return_value.all.return_value = []
            call_count["n"] += 1
            return result

        mock_session.execute = fake_execute
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routers.gateway.AsyncSessionLocal", return_value=ctx):
            result = await gw.manifest(x_api_key="oc-test")

    assert len(result.skills) == 1
    assert result.skills[0].name == "port-scan"
    assert result.skills[0].md_content == "# Port Scan\nRun nmap..."
    assert result.tools == []
    assert result.mcp_tools == []


@pytest.mark.asyncio
async def test_manifest_parses_tool_input_schema():
    """Tool.input_schema_json string is parsed to dict in the response."""
    from app.routers import gateway as gw

    fake_tool = SimpleNamespace(
        id=1, name="nmap", description="Net mapper",
        command_template="nmap -sV {target}",
        input_schema_json=json.dumps({"type": "object", "properties": {"target": {"type": "string"}}}),
    )
    agent = _fake_agent(tools=[1])

    mock_session = AsyncMock()
    call_count = {"n": 0}

    async def fake_execute(_q):
        result = MagicMock()
        # Second call is tools query
        if call_count["n"] == 1:
            result.scalars.return_value.all.return_value = [fake_tool]
        else:
            result.scalars.return_value.all.return_value = []
        call_count["n"] += 1
        return result

    mock_session.execute = fake_execute
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(gw, "_auth_agent", AsyncMock(return_value=agent)):
        with patch("app.routers.gateway.AsyncSessionLocal", return_value=ctx):
            result = await gw.manifest(x_api_key="oc-test")

    assert len(result.tools) == 1
    assert result.tools[0].input_schema == {"type": "object", "properties": {"target": {"type": "string"}}}
    assert result.tools[0].command_template == "nmap -sV {target}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gateway_manifest.py::test_manifest_empty_pools \
       tests/test_gateway_manifest.py::test_manifest_returns_assigned_skill \
       tests/test_gateway_manifest.py::test_manifest_parses_tool_input_schema -v
```

Expected: `AttributeError: module 'app.routers.gateway' has no attribute 'manifest'`

- [ ] **Step 3: Implement `GET /gateway/manifest` in `app/routers/gateway.py`**

Add these imports at the top of `app/routers/gateway.py` (after the existing imports):

```python
import json as _json

from app.models.mcp import MCPTool
from app.models.skill import Skill, Tool
from app.schemas.gateway import (
    ManifestMCPTool,
    ManifestResponse,
    ManifestSkill,
    ManifestTool,
)
```

Add the endpoint after `send_message` (at the end of the file):

```python
@router.get("/gateway/manifest", response_model=ManifestResponse)
async def manifest(x_api_key: str = Header(..., alias="X-Api-Key")):
    """Return the full manifest of skills/tools/mcp-tools assigned to this agent.

    The calling agent authenticates with the same X-Api-Key used for poll/report.
    An empty assignment list returns [] — the endpoint never falls back to the
    whole pool.
    """
    agent = await _auth_agent(x_api_key)

    skill_ids: list = agent.associated_skills or []
    tool_ids: list = agent.associated_tools or []
    mcp_ids: list = agent.associated_mcp_tools or []

    async with AsyncSessionLocal() as session:
        if skill_ids:
            rows = (await session.execute(
                select(Skill).where(Skill.is_active == True, Skill.id.in_(skill_ids))
            )).scalars().all()
        else:
            rows = []
        skills = [
            ManifestSkill(id=s.id, name=s.name, description=s.description, md_content=s.md_content)
            for s in rows
        ]

        if tool_ids:
            trows = (await session.execute(
                select(Tool).where(Tool.is_active == True, Tool.id.in_(tool_ids))
            )).scalars().all()
        else:
            trows = []
        tools = []
        for t in trows:
            try:
                schema = _json.loads(t.input_schema_json) if t.input_schema_json else {}
            except Exception:
                schema = {}
            tools.append(ManifestTool(
                id=t.id, name=t.name, description=t.description,
                command_template=t.command_template, input_schema=schema,
            ))

        if mcp_ids:
            mrows = (await session.execute(
                select(MCPTool).where(MCPTool.is_active == True, MCPTool.id.in_(mcp_ids))
            )).scalars().all()
        else:
            mrows = []
        mcp_tools = []
        for m in mrows:
            try:
                schema = _json.loads(m.input_schema_json) if m.input_schema_json else {}
            except Exception:
                schema = {}
            mcp_tools.append(ManifestMCPTool(
                id=m.id, name=m.tool_name, description=m.description, input_schema=schema,
            ))

    return ManifestResponse(
        agent_id=agent.id,
        agent_name=agent.agent_name,
        skills=skills,
        tools=tools,
        mcp_tools=mcp_tools,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_gateway_manifest.py::test_manifest_empty_pools \
       tests/test_gateway_manifest.py::test_manifest_returns_assigned_skill \
       tests/test_gateway_manifest.py::test_manifest_parses_tool_input_schema -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/routers/gateway.py tests/test_gateway_manifest.py
git commit -m "feat: add GET /gateway/manifest endpoint"
```

---

## Task 3: Add `has_manifest` to poll response

**Files:**
- Modify: `app/routers/gateway.py`
- Modify: `tests/test_gateway_manifest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gateway_manifest.py`:

```python
# ---------------------------------------------------------------------------
# Task 3 — Poll has_manifest field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_has_manifest_true_when_skills_assigned():
    """Poll response includes has_manifest=True when agent has skills assigned."""
    from app.routers import gateway as gw

    agent_with_skills = SimpleNamespace(
        id=5, agent_name="Bot",
        associated_skills=[1, 2],
        associated_tools=None,
        associated_mcp_tools=None,
    )

    fake_msg = SimpleNamespace(
        id=10, content="do task", execution_id="uuid-1",
        created_at=MagicMock(isoformat=lambda: "2026-05-30T00:00:00"),
    )

    mock_session = AsyncMock()
    msg_result = MagicMock()
    msg_result.scalars.return_value.all.return_value = [fake_msg]
    agent_result = MagicMock()
    agent_result.scalar_one_or_none.return_value = agent_with_skills

    async def fake_execute(q):
        r = MagicMock()
        # First execute = messages query, second = agent update query
        r.scalars.return_value.all.return_value = [fake_msg]
        r.scalar_one_or_none.return_value = agent_with_skills
        return r

    mock_session.execute = fake_execute
    mock_session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(gw, "_auth_agent", AsyncMock(return_value=agent_with_skills)):
        with patch("app.routers.gateway.AsyncSessionLocal", return_value=ctx):
            result = await gw.poll(x_api_key="oc-test")

    assert len(result.messages) == 1
    assert result.messages[0]["has_manifest"] is True


@pytest.mark.asyncio
async def test_poll_has_manifest_false_when_no_pools():
    """Poll response has has_manifest=False when agent has no pool assignments."""
    from app.routers import gateway as gw

    bare_agent = SimpleNamespace(
        id=5, agent_name="Bot",
        associated_skills=None,
        associated_tools=None,
        associated_mcp_tools=None,
    )

    mock_session = AsyncMock()

    async def fake_execute(_q):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.scalar_one_or_none.return_value = bare_agent
        return r

    mock_session.execute = fake_execute
    mock_session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(gw, "_auth_agent", AsyncMock(return_value=bare_agent)):
        with patch("app.routers.gateway.AsyncSessionLocal", return_value=ctx):
            result = await gw.poll(x_api_key="oc-test")

    assert result.messages == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gateway_manifest.py::test_poll_has_manifest_true_when_skills_assigned \
       tests/test_gateway_manifest.py::test_poll_has_manifest_false_when_no_pools -v
```

Expected: `FAILED` — `has_manifest` key not present in message dict

- [ ] **Step 3: Update the `poll` handler in `app/routers/gateway.py`**

In the `poll` function, before `return PollResponse(...)`, add:

```python
    has_manifest = bool(
        agent.associated_skills or agent.associated_tools or agent.associated_mcp_tools
    )
```

Then in the `PollResponse(messages=[...])` list comprehension, add `"has_manifest": has_manifest` to each message dict:

```python
    return PollResponse(
        messages=[
            {
                "id": m.id,
                "content": m.content,
                "execution_id": m.execution_id,
                "conversation_id": m.execution_id,
                "sender_user_name": "CyberGuard",
                "sender_user_id": 0,
                "created_at": m.created_at.isoformat(),
                "has_manifest": has_manifest,
            }
            for m in messages
        ]
    )
```

Note: `has_manifest` is computed from `agent` (the authenticated agent row loaded in `_auth_agent`). The `agent` variable in the poll handler is the return value of `await _auth_agent(x_api_key)` at line 97. Confirm that the `agent_row` re-fetched inside the session is the same object or re-read `associated_*` from the freshly fetched row if needed. Looking at the existing code: the poll handler calls `_auth_agent` which does its own DB query and returns an `AgentConfig` ORM row. That row has `associated_skills`/`associated_tools`/`associated_mcp_tools` columns. Use that `agent` directly.

The full updated return block:

```python
    return PollResponse(
        messages=[
            {
                "id": m.id,
                "content": m.content,
                "execution_id": m.execution_id,
                "conversation_id": m.execution_id,
                "sender_user_name": "CyberGuard",
                "sender_user_id": 0,
                "created_at": m.created_at.isoformat(),
                "has_manifest": has_manifest,
            }
            for m in messages
        ]
    )
```

Place the `has_manifest` computation right before the `return` (after the `await session.commit()`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_gateway_manifest.py::test_poll_has_manifest_true_when_skills_assigned \
       tests/test_gateway_manifest.py::test_poll_has_manifest_false_when_no_pools -v
```

Expected: both `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/routers/gateway.py tests/test_gateway_manifest.py
git commit -m "feat: add has_manifest flag to gateway poll response"
```

---

## Task 4: API key generation for all backends

**Files:**
- Modify: `app/routers/agents.py`
- Modify: `tests/test_gateway_manifest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gateway_manifest.py`:

```python
# ---------------------------------------------------------------------------
# Task 4 — API key for all backends
# ---------------------------------------------------------------------------

def test_create_custom_agent_issues_api_key():
    """Creating a custom agent returns an api_key (not just openclaw)."""
    # Test that `_generate_api_key` is called regardless of backend_type.
    # We test the router logic directly by inspecting the conditional.
    import ast, inspect
    from app.routers import agents as ag

    src = inspect.getsource(ag.create_agent)
    tree = ast.parse(src)

    # Walk the AST — there must be NO If node that checks backend_type == "openclaw"
    # before calling _generate_api_key.
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            cond = ast.dump(node.test)
            if "openclaw" in cond and "_generate_api_key" in ast.dump(node):
                raise AssertionError(
                    "create_agent still gates _generate_api_key behind backend_type == 'openclaw'"
                )


def test_regenerate_key_allows_non_openclaw():
    """regenerate_api_key endpoint no longer rejects non-openclaw agents."""
    import ast, inspect
    from app.routers import agents as ag

    src = inspect.getsource(ag.regenerate_api_key)
    # There must be no raise that checks backend_type != "openclaw"
    assert "Only openclaw" not in src, (
        "regenerate_api_key still contains 'Only openclaw' rejection message"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gateway_manifest.py::test_create_custom_agent_issues_api_key \
       tests/test_gateway_manifest.py::test_regenerate_key_allows_non_openclaw -v
```

Expected: `FAILED` — AST check finds the conditional / string still present

- [ ] **Step 3: Update `create_agent` in `app/routers/agents.py`**

Find this block (around line 183):

```python
    # OpenClaw 模式：生成 Gateway API Key
    plaintext_key: str | None = None
    if body.backend_type == "openclaw":
        plaintext_key, agent.api_key_hash = _generate_api_key()
```

Replace with:

```python
    # 所有 backend 生成 Gateway API Key（external agents 用此 key 调 /gateway/manifest 等接口）
    plaintext_key, agent.api_key_hash = _generate_api_key()
```

Also update the docstring for `create_agent` — change the paragraph that says "OpenClaw 模式：系统自动生成 `oc-xxx` API Key" to cover all backends:

```python
    """创建 Sub-Agent。

    所有 backend 创建时均自动生成 `oc-xxx` Gateway API Key，**只在此响应中返回一次**。
    外部节点用此 key 调用 /gateway/poll、/gateway/manifest 等接口。

    **OpenClaw 模式**（backend_type="openclaw"）：
    - `endpoint_url` 留空（OpenClaw 主动来轮询）。

    **其他模式**（hermes / custom）：
    - 填写 `endpoint_url`，CyberGuard 会主动 POST 到该地址。
    - 节点用返回的 `api_key` 调 /gateway/manifest 取资源上下文。

    **内部 Agent**（kind="internal"）：
    - 配置 LLM Provider，系统通过 Tool-Call 循环执行。
    """
```

- [ ] **Step 4: Update `regenerate_api_key` in `app/routers/agents.py`**

Find and remove (around line 285):

```python
    if agent.backend_type != "openclaw":
        raise HTTPException(status_code=400, detail="Only openclaw agents have a Gateway API Key")
```

Also update the docstring from "重新生成 OpenClaw Gateway API Key" to "重新生成 Gateway API Key".

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_gateway_manifest.py::test_create_custom_agent_issues_api_key \
       tests/test_gateway_manifest.py::test_regenerate_key_allows_non_openclaw -v
```

Expected: both `PASSED`

- [ ] **Step 6: Commit**

```bash
git add app/routers/agents.py tests/test_gateway_manifest.py
git commit -m "feat: issue API key to all agent backends on creation"
```

---

## Task 5: Inject `manifest_url` in `SubAgentWrapper.execute`

**Files:**
- Modify: `app/services/agent_executor.py`
- Modify: `tests/test_gateway_manifest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gateway_manifest.py`:

```python
# ---------------------------------------------------------------------------
# Task 5 — SubAgentWrapper manifest_url injection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subagent_wrapper_injects_manifest_url_when_base_url_set():
    """When settings.BASE_URL is set, execute payload contains manifest_url."""
    import httpx
    from app.services.agent_executor import SubAgentWrapper

    config = {
        "id": 3,
        "agent_name": "BotX",
        "backend_type": "custom",
        "endpoint_url": "https://bot.example.com",
        "env_vars_encrypted": None,
    }

    captured = {}

    async def fake_post(url, headers=None, json=None, **kw):
        captured["payload"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"output": "done"}
        return resp

    with patch("app.config.settings.BASE_URL", "https://cyberguard.example.com"):
        wrapper = SubAgentWrapper(config)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await wrapper.execute(task="scan 10.0.0.1", context={"user_id": 1})

    assert "manifest_url" in captured["payload"]
    assert captured["payload"]["manifest_url"] == (
        "https://cyberguard.example.com/api/v1/gateway/manifest"
    )


@pytest.mark.asyncio
async def test_subagent_wrapper_omits_manifest_url_when_base_url_empty():
    """When settings.BASE_URL is empty, manifest_url is not in the payload."""
    from app.services.agent_executor import SubAgentWrapper

    config = {
        "id": 3,
        "agent_name": "BotX",
        "backend_type": "custom",
        "endpoint_url": "https://bot.example.com",
        "env_vars_encrypted": None,
    }

    captured = {}

    async def fake_post(url, headers=None, json=None, **kw):
        captured["payload"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"output": "done"}
        return resp

    with patch("app.config.settings.BASE_URL", ""):
        wrapper = SubAgentWrapper(config)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await wrapper.execute(task="scan 10.0.0.1", context={"user_id": 1})

    assert "manifest_url" not in captured["payload"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gateway_manifest.py::test_subagent_wrapper_injects_manifest_url_when_base_url_set \
       tests/test_gateway_manifest.py::test_subagent_wrapper_omits_manifest_url_when_base_url_empty -v
```

Expected: `FAILED` — `manifest_url` not in payload

- [ ] **Step 3: Update `SubAgentWrapper.execute` in `app/services/agent_executor.py`**

In the `execute` method (around line 140), find the payload construction:

```python
        payload = {
            "task": task,
            "context": context or {},
            "env_vars": self.env_vars,
            "timestamp": datetime.utcnow().isoformat(),
        }
```

Replace with:

```python
        payload = {
            "task": task,
            "context": context or {},
            "env_vars": self.env_vars,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if settings.BASE_URL:
            payload["manifest_url"] = (
                f"{settings.BASE_URL.rstrip('/')}/api/v1/gateway/manifest"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_gateway_manifest.py::test_subagent_wrapper_injects_manifest_url_when_base_url_set \
       tests/test_gateway_manifest.py::test_subagent_wrapper_omits_manifest_url_when_base_url_empty -v
```

Expected: both `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/services/agent_executor.py tests/test_gateway_manifest.py
git commit -m "feat: inject manifest_url in SubAgentWrapper payload when BASE_URL is set"
```

---

## Task 6: Refactor `get_mcp_tools_for_agent` to read `associated_mcp_tools` column

**Files:**
- Modify: `app/services/agent_executor.py`
- Modify: `tests/test_gateway_manifest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gateway_manifest.py`:

```python
# ---------------------------------------------------------------------------
# Task 6 — get_mcp_tools_for_agent refactor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_mcp_tools_reads_associated_column_first():
    """Uses agent_associated_mcp_tools list, ignoring metadata fallback."""
    from app.services.agent_executor import AgentExecutor

    fake_mcp = SimpleNamespace(
        id=5, tool_name="search_cve", description="CVE lookup",
        input_schema_json='{"type": "object"}',
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_mcp]
    mock_session.execute = AsyncMock(return_value=mock_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.agent_executor.get_db_context", return_value=ctx):
        executor = AgentExecutor()
        tools = await executor.get_mcp_tools_for_agent(
            agent_associated_mcp_tools=[5],
            agent_metadata_json={"mcp_tool_ids": [99]},  # should be ignored
        )

    assert len(tools) == 1
    assert tools[0]["name"] == "search_cve"
    assert tools[0]["input_schema"] == {"type": "object"}

    # Verify the query used id=5 (from associated column), not id=99 (from metadata)
    call_args = mock_session.execute.call_args[0][0]
    compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
    assert "5" in compiled
    assert "99" not in compiled


@pytest.mark.asyncio
async def test_get_mcp_tools_falls_back_to_metadata_when_column_is_none():
    """Falls back to metadata_json.mcp_tool_ids when associated column is None."""
    from app.services.agent_executor import AgentExecutor

    fake_mcp = SimpleNamespace(
        id=99, tool_name="old_tool", description="Legacy",
        input_schema_json=None,
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_mcp]
    mock_session.execute = AsyncMock(return_value=mock_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.agent_executor.get_db_context", return_value=ctx):
        executor = AgentExecutor()
        tools = await executor.get_mcp_tools_for_agent(
            agent_associated_mcp_tools=None,       # column not set
            agent_metadata_json={"mcp_tool_ids": [99]},  # use this
        )

    assert len(tools) == 1
    assert tools[0]["name"] == "old_tool"
    assert tools[0]["input_schema"] == {}  # None schema becomes empty dict


@pytest.mark.asyncio
async def test_get_mcp_tools_returns_all_when_both_none():
    """When both column and metadata are None, returns all active MCP tools."""
    from app.services.agent_executor import AgentExecutor

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.agent_executor.get_db_context", return_value=ctx):
        executor = AgentExecutor()
        tools = await executor.get_mcp_tools_for_agent(
            agent_associated_mcp_tools=None,
            agent_metadata_json=None,
        )

    # No .where(id.in_(...)) clause — query fetches all active tools
    call_args = mock_session.execute.call_args[0][0]
    compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
    assert "IN" not in compiled.upper()
    assert tools == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gateway_manifest.py::test_get_mcp_tools_reads_associated_column_first \
       tests/test_gateway_manifest.py::test_get_mcp_tools_falls_back_to_metadata_when_column_is_none \
       tests/test_gateway_manifest.py::test_get_mcp_tools_returns_all_when_both_none -v
```

Expected: `FAILED` — old signature `(agent_metadata_json=...)` doesn't match

- [ ] **Step 3: Refactor `get_mcp_tools_for_agent` in `app/services/agent_executor.py`**

Replace the existing method (lines 254–285):

```python
    async def get_mcp_tools_for_agent(
        self,
        agent_associated_mcp_tools: Optional[List[int]] = None,
        agent_metadata_json: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch active MCP tools for an agent and convert to OpenClaw tool format.

        Priority:
          1. agent_associated_mcp_tools (new column) — filter to these IDs
          2. agent_metadata_json.mcp_tool_ids (legacy key) — filter to these IDs
          3. Neither set — return all active MCP tools
        """
        from app.core.database import get_db_context
        from app.models.mcp import MCPTool
        from sqlalchemy import select
        import json

        # Determine which IDs to filter by (None = no filter = all active tools)
        tool_ids = agent_associated_mcp_tools
        if tool_ids is None and agent_metadata_json:
            tool_ids = agent_metadata_json.get("mcp_tool_ids")

        async with get_db_context() as session:
            query = select(MCPTool).where(MCPTool.is_active == True)
            if tool_ids is not None:
                query = query.where(MCPTool.id.in_(tool_ids))
            result = await session.execute(query)
            tools = result.scalars().all()

        openclaw_tools = []
        for t in tools:
            try:
                input_schema = json.loads(t.input_schema_json) if t.input_schema_json else {}
            except Exception:
                input_schema = {}
            openclaw_tools.append({
                "name": t.tool_name,
                "description": t.description or "",
                "input_schema": input_schema,
            })
        return openclaw_tools
```

- [ ] **Step 4: Verify no call sites need updating**

```bash
grep -rn "get_mcp_tools_for_agent" /Users/jc/Documents/cyber-agent/cyberguard/app/
```

Expected: only the definition line in `agent_executor.py`. The method has no callers in production code — `InternalAgentRunner._load_mcp_tools` (in `internal_agent.py`) already reads `associated_mcp_tools` directly at line 68. No other files need changes.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_gateway_manifest.py::test_get_mcp_tools_reads_associated_column_first \
       tests/test_gateway_manifest.py::test_get_mcp_tools_falls_back_to_metadata_when_column_is_none \
       tests/test_gateway_manifest.py::test_get_mcp_tools_returns_all_when_both_none -v
```

Expected: all `PASSED`

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/test_gateway_manifest.py tests/test_tool_executor.py -v
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add app/services/agent_executor.py tests/test_gateway_manifest.py
git commit -m "refactor: get_mcp_tools_for_agent reads associated_mcp_tools column first"
```

---

## Final Verification

- [ ] **Run all tests**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
pytest tests/test_gateway_manifest.py tests/test_tool_executor.py -v
```

Expected: all tests pass, no errors

- [ ] **Check no old patterns remain**

```bash
# Should print nothing (no remaining openclaw-only gate in regenerate-key)
grep -n "Only openclaw" app/routers/agents.py

# Should print nothing (no remaining openclaw-only gate in create_agent)
grep -A3 "if body.backend_type" app/routers/agents.py | grep "openclaw" || echo "clean"

# Should show manifest endpoint exists
grep -n "def manifest" app/routers/gateway.py

# Should show has_manifest in poll
grep -n "has_manifest" app/routers/gateway.py
```
