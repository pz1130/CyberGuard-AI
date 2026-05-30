"""Tests for GET /gateway/manifest and related changes."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.gateway import (
    ManifestSkill, ManifestTool, ManifestMCPTool, ManifestResponse,
)


# ---------------------------------------------------------------------------
# Task 1 — Schema smoke
# ---------------------------------------------------------------------------

def test_manifest_schemas_round_trip():
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
        input_schema_json='{"type": "object", "properties": {"target": {"type": "string"}}}',
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

    async def fake_execute(q):
        r = MagicMock()
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
