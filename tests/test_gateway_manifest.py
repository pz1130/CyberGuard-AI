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
