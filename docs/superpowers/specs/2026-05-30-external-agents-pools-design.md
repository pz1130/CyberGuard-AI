---
name: external-agents-pools-design
description: Subproject ③ of the QwenPaw pool alignment — deliver assigned skills/tools/mcp context to external agents via a /gateway/manifest endpoint; extend API key generation to all backends.
type: design
date: 2026-05-30
status: approved
---

# External Agents Using Pools (subproject ③)

## Context

Subprojects ① and ② built the executable Tool pool and unified `associated_skills`,
`associated_tools`, `associated_mcp_tools` columns on `AgentConfig`. Internal agents
already read these columns to build their runtime context. External agents (OpenClaw,
Custom, Hermes) currently ignore them entirely.

This subproject (③) makes those assignments visible and actionable for external agents:
any registered external node can fetch the manifest of resources assigned to it, and
use that context when executing tasks.

## Goals

1. All agent backends (not just OpenClaw) are issued a CyberGuard API key on creation,
   enabling them to authenticate against gateway endpoints.
2. New `GET /gateway/manifest` endpoint returns the full skills/tools/mcp-tools
   assigned to the calling agent.
3. OpenClaw poll responses signal `has_manifest: true` when any pool assignment exists.
4. `SubAgentWrapper` (Custom/Hermes push path) injects `manifest_url` into the task
   payload when `settings.BASE_URL` is configured.
5. `AgentExecutor.get_mcp_tools_for_agent` is refactored to read `associated_mcp_tools`
   column first, falling back to `metadata_json.mcp_tool_ids` for safety.

## Non-goals

- Gateway callbacks for tool execution — agents execute tools locally using the
  schemas delivered by the manifest.
- WebUI indicator for "Custom agent needs API key" (admin uses regenerate-key API).
- MCP tool execution proxying.
- Manifest caching / ETags (YAGNI at current scale).

## Detailed Design

### 1. API key extension to all backends

**File:** `app/routers/agents.py`

The agent creation handler currently gates API key generation behind
`if body.backend_type == "openclaw"`. Remove that condition so every
`POST /agents` request generates an `oc-xxx` key, stores its SHA-256 hash in
`api_key_hash`, and returns the plaintext key in the response (one-time).

The existing `POST /agents/{id}/regenerate-key` endpoint rejects non-openclaw agents
with HTTP 400. Remove that check — all backends can regenerate.

No DB migration required; `api_key_hash` is already a nullable column on
`agent_configs`.

**Backward compatibility:** existing Custom/Hermes rows have `api_key_hash = NULL`.
They cannot call `/gateway/manifest` until an admin regenerates their key. This is
acceptable — pool assignment for those agents is also likely empty today.

### 2. `GET /gateway/manifest` endpoint

**File:** `app/routers/gateway.py`

```
GET /api/v1/gateway/manifest
X-Api-Key: oc-<token>
```

Authentication reuses the existing `_auth_agent(x_api_key)` helper.

**Response schema:**

```json
{
  "agent_id": 7,
  "agent_name": "ScanBot",
  "skills": [
    {
      "id": 3,
      "name": "port-scan",
      "description": "Port scanning runbook",
      "md_content": "# Port Scan\n..."
    }
  ],
  "tools": [
    {
      "id": 1,
      "name": "nmap",
      "description": "Network mapper",
      "command_template": "nmap -sV -p {ports} {target}",
      "input_schema": { "type": "object", "properties": { "ports": { "type": "string" }, "target": { "type": "string" } } }
    }
  ],
  "mcp_tools": [
    {
      "id": 5,
      "name": "search_cve",
      "description": "Search CVE database",
      "input_schema": { "type": "object" }
    }
  ]
}
```

**Implementation:**

- Read `agent.associated_skills`, `agent.associated_tools`, `agent.associated_mcp_tools`
  from the authenticated `AgentConfig` row.
- For each non-empty ID list, batch-query the respective model filtered by
  `is_active == True`. IDs that no longer exist or are inactive are silently skipped.
- An empty assignment list returns `[]` for that array — never falls back to returning
  all pool items.
- `Tool.input_schema_json` (a JSON string) is parsed to a dict before inclusion.
- `md_content` is returned in full (not truncated).

**New Pydantic schemas** — add to new file `app/schemas/gateway.py`, imported by the router:

```python
class ManifestSkill(BaseModel):
    id: int; name: str; description: Optional[str]; md_content: str

class ManifestTool(BaseModel):
    id: int; name: str; description: Optional[str]
    command_template: Optional[str]; input_schema: dict

class ManifestMCPTool(BaseModel):
    id: int; name: str; description: Optional[str]; input_schema: dict

class ManifestResponse(BaseModel):
    agent_id: int; agent_name: str
    skills: list[ManifestSkill]
    tools: list[ManifestTool]
    mcp_tools: list[ManifestMCPTool]
```

### 3. OpenClaw poll — `has_manifest` signal

**File:** `app/routers/gateway.py` — `poll` handler

After loading the agent row, compute:
```python
has_manifest = any([
    agent.associated_skills,
    agent.associated_tools,
    agent.associated_mcp_tools,
])
```

Add `"has_manifest": has_manifest` to each message dict in the `PollResponse`. This
field is computed dynamically; nothing is stored in `GatewayMessage`.

### 4. Custom/Hermes payload — `manifest_url` injection

**File:** `app/services/agent_executor.py` — `SubAgentWrapper.execute`

**Config:** add `BASE_URL: str = ""` to `app/config.py` (`Settings` class).

When building the outgoing payload:
```python
payload = {
    "task": task,
    "context": context or {},
    "env_vars": self.env_vars,
    "timestamp": datetime.utcnow().isoformat(),
}
if settings.BASE_URL:
    payload["manifest_url"] = f"{settings.BASE_URL.rstrip('/')}/api/v1/gateway/manifest"
```

When `BASE_URL` is empty (default), the field is absent and existing Custom nodes
are unaffected.

### 5. `get_mcp_tools_for_agent` refactor

**File:** `app/services/agent_executor.py`

Update signature and priority logic:

```python
async def get_mcp_tools_for_agent(
    self,
    agent_associated_mcp_tools: Optional[List[int]] = None,
    agent_metadata_json: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    # Column-first, metadata fallback
    tool_ids = agent_associated_mcp_tools
    if tool_ids is None and agent_metadata_json:
        tool_ids = agent_metadata_json.get("mcp_tool_ids")

    async with get_db_context() as session:
        query = select(MCPTool).where(MCPTool.is_active == True)
        if tool_ids is not None:
            query = query.where(MCPTool.id.in_(tool_ids))
        result = await session.execute(query)
        tools = result.scalars().all()
    ...
```

Update the call site in `AgentExecutor.execute` to pass
`agent_associated_mcp_tools=config_dict["associated_mcp_tools"]`.

## Error Handling

| Scenario | Behaviour |
|---|---|
| Invalid / missing `X-Api-Key` | 401 (existing `_auth_agent` logic) |
| All three pool columns are `NULL` / empty | 200 with three empty arrays |
| An assigned ID no longer exists or is inactive | Silently skipped |
| `BASE_URL` not set | `manifest_url` omitted from Custom payload |
| Existing Custom agent has no `api_key_hash` | 401 on `/gateway/manifest`; admin must call `regenerate-key` |

## Files Changed

| File | Change |
|---|---|
| `app/routers/agents.py` | Remove `backend_type == "openclaw"` gate on key generation and regenerate-key endpoint |
| `app/routers/gateway.py` | Add `GET /gateway/manifest`; add `has_manifest` to poll response |
| `app/services/agent_executor.py` | Refactor `get_mcp_tools_for_agent`; inject `manifest_url` in `SubAgentWrapper.execute` |
| `app/config.py` | Add `BASE_URL: str = ""` |
| `app/schemas/` | Add `ManifestSkill`, `ManifestTool`, `ManifestMCPTool`, `ManifestResponse` |

No DB migration required.
