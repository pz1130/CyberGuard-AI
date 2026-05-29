---
name: pool-assignment-tags-design
description: Subproject ② of the QwenPaw pool alignment — unify skill/tool/mcp assignment on AgentConfig as three first-class columns, add tags to the three pools, and give internal agents a WebUI assignment panel.
type: design
date: 2026-05-29
status: approved-pending-review
---

# Unified Pool Assignment + Tags (subproject ②)

## Context

Subproject ① made the Tool pool executable and wired it into the internal agent
via a **temporary** `metadata_json.tool_ids` list. Assignment across the three
pools is currently inconsistent:

- `AgentConfig.associated_skills` — a first-class JSON column (list of skill IDs).
- `metadata_json.mcp_tool_ids` — MCP tools, stashed in the metadata blob.
- `metadata_json.tool_ids` — executable Tools (the ① temporary key).

Pools also lack discovery metadata: `Skill`/`Tool` have a `version` column,
`MCPTool` has none, and none have `tags`.

This subproject (②) unifies assignment into three symmetric first-class columns,
adds `tags` to all three pools, and gives **internal agents** a WebUI panel to
pick skills/tools/mcp tools. External agents using the pools is subproject ③.

## Goals

1. `AgentConfig` gains `associated_tools` and `associated_mcp_tools` JSON columns
   (mirroring `associated_skills`), with a data migration that moves existing
   `metadata_json.tool_ids` / `metadata_json.mcp_tool_ids` into them.
2. `Skill`, `Tool`, `MCPTool` each gain a `tags` JSON array column.
3. Read points (`InternalAgentRunner`, `AgentExecutor`) consume the new columns,
   with a fallback to the old `metadata_json` keys for safety during rollout.
4. Pool CRUD APIs accept/return `tags`; pool list endpoints support `?tag=` filtering.
5. Agent CRUD APIs accept/return the two new assignment lists.
6. WebUI: internal-agent edit form gets three multi-select assignment panels
   (Skills / Tools / MCP tools); each pool page gets a tags editor + tag filter
   and shows `version` where it exists.

## Non-goals (deferred)

- External agents (OpenClaw/Custom) using the pools — payload delivery + gateway
  callbacks → subproject ③.
- `version` on MCP (YAGNI) and any version-bump/lifecycle workflow.
- Multi-file skill artifacts / filesystem provisioning (out of scope overall).

## Detailed design

### 1. Data model + migration 012

`app/models/agent.py` — `AgentConfig` adds:
```python
    associated_tools = Column(JSON, nullable=True)       # List[int] Tool IDs
    associated_mcp_tools = Column(JSON, nullable=True)   # List[int] MCPTool IDs
```
`app/models/skill.py` — `Skill` and `Tool` each add:
```python
    tags = Column(JSON, nullable=True)   # List[str]
```
`app/models/mcp.py` — `MCPTool` adds:
```python
    tags = Column(JSON, nullable=True)   # List[str]
```

`alembic/versions/012_pool_assignment_tags.py` (down_revision `011_tool_executable`):
- `add_column` the two `agent_configs` columns and the three `tags` columns.
- **Data migration** in `upgrade()`: for each `agent_configs` row, read
  `metadata_json` (JSON); if it contains `tool_ids`, copy to `associated_tools`;
  if it contains `mcp_tool_ids`, copy to `associated_mcp_tools`; then **remove
  those two keys from `metadata_json`** and write the cleaned metadata back, so the
  ids live in exactly one place. Use a data-only loop via `op.get_bind()` + raw
  SELECT/UPDATE; handle `metadata_json` being a dict, a JSON string, or null.
- `downgrade()`: reversible — for each row, move `associated_tools` →
  `metadata_json["tool_ids"]` and `associated_mcp_tools` →
  `metadata_json["mcp_tool_ids"]` (only when non-empty), then drop the five
  columns. This restores the pre-migration shape so no assignment is lost on
  rollback.

Because the metadata keys are removed on upgrade, the read-point metadata
fallback (below) is normally never hit; it is kept purely as defensive cover for
rows created in the brief window between code deploy and migration, and for
rollback safety.

### 2. Read-point changes

`app/services/internal_agent.py` `__init__` — prefer the columns, fall back to
metadata for un-migrated rows:
```python
        self.associated_skills = config.get("associated_skills") or []
        self.pool_tool_ids = config.get("associated_tools") or meta.get("tool_ids") or []
        self.mcp_tool_ids = config.get("associated_mcp_tools") or meta.get("mcp_tool_ids") or []
```
(The existing `_load_pool_tools` / `_load_mcp_tools` / dispatch logic is unchanged
— only the source of the id lists changes. The `tool_ids` self-attribute name
`pool_tool_ids` stays.)

`app/services/agent_executor.py`:
- `config_dict` (in `execute`) adds `associated_tools` and `associated_mcp_tools`
  from the `AgentConfig` row, so `InternalAgentRunner` receives them. This is the
  essential ② read-point change for the internal-agent path.
- `get_mcp_tools_for_agent(...)` is the **external** OpenClaw tool-delivery helper
  (used by subproject ③, not the internal path). Leave it as-is in ②; ③ will
  refactor it to read `associated_mcp_tools`. (Confirm via grep that it is not on
  the internal-agent execution path before deciding to touch it — if it has no
  current callers, do not modify it in ②.)

### 3. Schemas

`app/schemas/agent.py` — the create/update/read models add:
```python
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
```
`app/schemas/skill.py` (`Skill*` and `Tool*`) and the MCP tool schema add:
```python
    tags: Optional[List[str]] = None
```

### 4. API

- `Skill`/`Tool`/`MCPTool` create+update accept `tags`; read returns `tags`.
- Pool list endpoints (`GET /skills`, `GET /tools`, and the MCP tools list) accept
  an optional `tag: str | None` query param; when set, filter to rows whose `tags`
  JSON array contains that tag (in Python after fetch, or a JSON containment
  query — Python filter is fine for these small pools).
- Agent create+update accept the two new assignment lists; read returns them.
- Assignment validation: the kind-aware agent validation is unchanged; the new
  lists are optional and default to empty.

### 5. WebUI

Internal-agent assignment panel (Agents page edit/create form, internal kind only):
- Three multi-select controls — Skills, Tools, MCP tools — populated from
  `getSkills()`, `getTools()`, and the MCP tools list endpoint. Each option shows
  name + tags (+ version where present). Selected IDs are sent as
  `associated_skills` / `associated_tools` / `associated_mcp_tools` in the agent
  payload. On edit, pre-select from the agent's current lists.
- Keep it simple: checkboxes or a multi-select list per pool (reuse existing form
  styling; no fancy transfer widget).

Pool pages (Skills, Tools, MCP):
- Form: a `tags` editor (comma-separated input → string array, or simple chips).
- List: a tag filter (dropdown/typeahead of known tags, or a text box) calling the
  `?tag=` API; show the existing `version` on Skill/Tool cards.

## Data flow

Assignment write: WebUI agent form → agent CRUD API → `associated_*` columns.
Assignment read (internal agent run): `AgentExecutor.execute` loads the columns
into `config_dict` → `InternalAgentRunner` reads them (column-first, metadata
fallback) → builds the tool catalogue (skills into prompt; tools + mcp as callable
tools, exactly as in ①).

## Error handling

- Missing/empty assignment lists → treated as empty (no tools), as today.
- Referenced IDs that no longer exist or are inactive → silently skipped by the
  existing `_load_*` queries (they filter `is_active == True` / existence).
- `tags` not a list → coerced to empty list on read.
- The migration handles `metadata_json` being a dict, a JSON string, or null.

## Testing

Unit / pure-logic (stable, no DB-event-loop issue):
- `InternalAgentRunner.__init__` id-source precedence: column value wins; falls
  back to metadata when the column is empty (construct with cfg dicts, assert the
  resolved `pool_tool_ids` / `mcp_tool_ids` / `associated_skills`).
- `get_mcp_tools_for_agent(mcp_tool_ids=[...])` filters to those ids (mock DB or
  small fixture).
- Pool `?tag=` filter returns only rows containing the tag.

DB-backed (mark / run individually per the known pytest-asyncio isolation issue):
- Migration round-trip: an agent row with `metadata_json={"tool_ids":[1],"mcp_tool_ids":[2]}`
  ends up with `associated_tools=[1]`, `associated_mcp_tools=[2]` after upgrade.
- Agent create with assignment lists persists + reads back.

WebUI: type-check (`tsc --noEmit`); manual: edit an internal agent, assign a
skill+tool+mcp tool, save, reopen → selections persist; add a tag to a tool, filter
by it.

## Migration / rollout

1. Alembic migration 012 (columns + data move). Rebuild api image (alembic baked in).
2. Read points deploy with column-first + metadata fallback, so old rows keep
   working even before/after the data move.
3. WebUI rebuild for the assignment panel + tags.

## Open questions

None — resolved during brainstorming (full symmetric three columns; tags on all
three pools, version unchanged with MCP getting none; assignment UI for internal
agents only).
