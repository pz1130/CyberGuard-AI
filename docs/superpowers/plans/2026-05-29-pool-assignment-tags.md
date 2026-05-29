# Unified Pool Assignment + Tags (subproject ②) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify skill/tool/mcp assignment into three first-class `AgentConfig` columns, add `tags` to the three pools, and give internal agents a WebUI assignment panel.

**Architecture:** Add `associated_tools` + `associated_mcp_tools` JSON columns to `AgentConfig` (mirroring `associated_skills`) with a data migration that moves ids out of `metadata_json` and cleans the old keys. Add `tags` JSON columns to `Skill`/`Tool`/`MCPTool`. Read points read columns-first with a metadata fallback. Agent + pool CRUD persist/return the new fields automatically (create builds via `hasattr` filter, update via `setattr`, once model+schema have the fields). WebUI: internal-agent form gets three multi-select pickers; pool pages get a tags editor + `?tag=` filter.

**Tech Stack:** SQLAlchemy (async) + Alembic, FastAPI, pytest, React/TS WebUI. Spec: `docs/superpowers/specs/2026-05-29-pool-assignment-tags-design.md`.

---

## File structure

- `app/models/agent.py` — `AgentConfig` gains two assignment columns (modify).
- `app/models/skill.py` — `Skill` + `Tool` gain `tags` (modify).
- `app/models/mcp.py` — `MCPTool` gains `tags` (modify).
- `alembic/versions/012_pool_assignment_tags.py` — columns + data move (create).
- `app/schemas/agent.py` — assignment fields on Base/Update/Read (modify).
- `app/schemas/skill.py` — `tags` on Skill*/Tool* schemas (modify).
- `app/schemas/mcp.py` — `tags` on MCPTool* schemas (modify).
- `app/services/internal_agent.py` — column-first id resolution (modify).
- `app/services/agent_executor.py` — config_dict carries the two columns (modify).
- `app/routers/skills.py` — `?tag=` filter on `/skills` + `/tools` (modify).
- `app/routers/mcp.py` — `?tag=` filter on `/mcp/tools/all` (modify).
- `tests/test_internal_agent.py` — id-source precedence tests (modify).
- `webui/src/pages/Agents.tsx` — internal-agent assignment pickers (modify).
- `webui/src/api/client.ts` — ensure getSkills/getTools/getAllMcpTools (modify).
- `webui/src/pages/Skills.tsx`, `Tools.tsx`, `MCP.tsx` — tags editor + filter (modify).

Note on test harness (api container): `docker compose exec -T api pip install -q pytest pytest-asyncio` once; before each run `docker compose exec -T api rm -rf /app/tests && docker cp tests cyberguard-api-1:/app/tests`. The DB-async event-loop isolation issue (see project_status.md) affects DB-backed tests run together — the new precedence tests are pure-logic and unaffected; API behavior is verified with live curl like subproject ①.

---

## Task 1: Model columns + migration 012

**Files:**
- Modify: `app/models/agent.py`, `app/models/skill.py`, `app/models/mcp.py`
- Create: `alembic/versions/012_pool_assignment_tags.py`

- [ ] **Step 1: Add the AgentConfig assignment columns**

In `app/models/agent.py`, right after the existing `associated_skills = Column(JSON, nullable=True)  # List of skill IDs` line, add:

```python
    associated_tools = Column(JSON, nullable=True)       # List of Tool IDs
    associated_mcp_tools = Column(JSON, nullable=True)   # List of MCPTool IDs
```

- [ ] **Step 2: Add tags to Skill, Tool, MCPTool**

In `app/models/skill.py`, add to BOTH the `Skill` class and the `Tool` class (e.g. after their `metadata_json` column):

```python
    tags = Column(JSON, nullable=True)  # List[str]
```

In `app/models/mcp.py`, add to the `MCPTool` class (e.g. after `category`):

```python
    tags = Column(JSON, nullable=True)  # List[str]
```

- [ ] **Step 3: Write migration 012 (columns + data move + reversible downgrade)**

Create `alembic/versions/012_pool_assignment_tags.py`:

```python
"""unified pool assignment columns + pool tags

Revision ID: 012_pool_assignment_tags
Revises: 011_tool_executable
Create Date: 2026-05-29
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "012_pool_assignment_tags"
down_revision = "011_tool_executable"
branch_labels = None
depends_on = None


def _as_dict(meta):
    if meta is None:
        return None
    if isinstance(meta, dict):
        return dict(meta)
    if isinstance(meta, str):
        try:
            d = json.loads(meta)
            return d if isinstance(d, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def upgrade() -> None:
    op.add_column("agent_configs", sa.Column("associated_tools", sa.JSON(), nullable=True))
    op.add_column("agent_configs", sa.Column("associated_mcp_tools", sa.JSON(), nullable=True))
    op.add_column("skills", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("tools", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("mcp_tools", sa.Column("tags", sa.JSON(), nullable=True))

    # Move tool_ids / mcp_tool_ids out of metadata_json into the new columns,
    # then remove those keys from metadata_json.
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, metadata_json FROM agent_configs")).fetchall()
    for rid, meta in rows:
        d = _as_dict(meta)
        if not d:
            continue
        tool_ids = d.pop("tool_ids", None)
        mcp_ids = d.pop("mcp_tool_ids", None)
        if tool_ids is None and mcp_ids is None:
            continue
        conn.execute(
            text("UPDATE agent_configs SET "
                 "associated_tools = CAST(:t AS JSON), "
                 "associated_mcp_tools = CAST(:m AS JSON), "
                 "metadata_json = CAST(:meta AS JSON) WHERE id = :id"),
            {"t": json.dumps(tool_ids) if tool_ids is not None else None,
             "m": json.dumps(mcp_ids) if mcp_ids is not None else None,
             "meta": json.dumps(d), "id": rid},
        )


def downgrade() -> None:
    # Move the column values back into metadata_json so rollback loses nothing.
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT id, metadata_json, associated_tools, associated_mcp_tools "
             "FROM agent_configs")).fetchall()
    for rid, meta, tool_ids, mcp_ids in rows:
        if tool_ids is None and mcp_ids is None:
            continue
        d = _as_dict(meta) or {}
        if tool_ids is not None:
            d["tool_ids"] = tool_ids if not isinstance(tool_ids, str) else json.loads(tool_ids)
        if mcp_ids is not None:
            d["mcp_tool_ids"] = mcp_ids if not isinstance(mcp_ids, str) else json.loads(mcp_ids)
        conn.execute(
            text("UPDATE agent_configs SET metadata_json = CAST(:meta AS JSON) WHERE id = :id"),
            {"meta": json.dumps(d), "id": rid},
        )
    op.drop_column("mcp_tools", "tags")
    op.drop_column("tools", "tags")
    op.drop_column("skills", "tags")
    op.drop_column("agent_configs", "associated_mcp_tools")
    op.drop_column("agent_configs", "associated_tools")
```

- [ ] **Step 4: Apply and verify**

Run: `docker compose build api && docker compose up -d api && sleep 4 && docker compose exec -T api alembic upgrade head`
Expected: head is `012_pool_assignment_tags`.
Run: `docker compose exec -T postgres psql -U postgres -d cyberguard -c "\d agent_configs" | grep associated_`
Expected: shows `associated_tools` and `associated_mcp_tools`.
Run: `docker compose exec -T postgres psql -U postgres -d cyberguard -c "\d tools" | grep tags`
Expected: shows `tags`.

- [ ] **Step 5: Verify the data move on an existing internal agent (if any)**

Run:
```bash
docker compose exec -T postgres psql -U postgres -d cyberguard -c "SELECT id, metadata_json, associated_tools, associated_mcp_tools FROM agent_configs WHERE metadata_json::text LIKE '%tool_ids%' OR associated_tools IS NOT NULL;"
```
Expected: no rows still contain `tool_ids`/`mcp_tool_ids` inside `metadata_json` (they moved to the columns). If there were none to begin with, that's fine.

- [ ] **Step 6: Commit**

```bash
git add app/models/agent.py app/models/skill.py app/models/mcp.py alembic/versions/012_pool_assignment_tags.py
git commit -m "feat(pools): assignment columns + pool tags + migration 012 (move ids out of metadata)"
```

---

## Task 2: Schemas — assignment fields + tags

**Files:**
- Modify: `app/schemas/agent.py`, `app/schemas/skill.py`, `app/schemas/mcp.py`

- [ ] **Step 1: Agent schemas**

In `app/schemas/agent.py`, add the two assignment fields next to each existing `associated_skills` line. In `AgentConfigBase` (after `associated_skills: Optional[List[int]] = None`):

```python
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
```

In `AgentConfigUpdate` (after its `associated_skills: Optional[List[int]] = None`):

```python
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
```

In `AgentConfigRead` (after its `associated_skills: Optional[List[int]]`):

```python
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
```

- [ ] **Step 2: Pool tags — skill schemas**

In `app/schemas/skill.py`, add `tags: Optional[List[str]] = None` to: `SkillBase`, `SkillResponse`, `ToolBase`, `ToolResponse`. Also add it to `SkillUpdate` and `ToolUpdate` (so tags can be edited). (`List` is already imported in that file.)

- [ ] **Step 3: Pool tags — mcp tool schemas**

In `app/schemas/mcp.py`, add `tags: Optional[List[str]] = None` to `MCPToolBase`, `MCPToolResponse`, and `MCPToolUpdate`. Ensure `List` is imported (`from typing import ... List`); if not, add it.

- [ ] **Step 4: Smoke-check imports**

Run: `docker compose restart api && sleep 4 && docker compose exec -T api python -c "from app.schemas.agent import AgentConfigCreate; from app.schemas.skill import ToolCreate; from app.schemas.mcp import MCPToolCreate; print(AgentConfigCreate(agent_name='x', backend_type='openclaw').associated_tools, ToolCreate(name='t').tags)"`
Expected: prints `None None`.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/agent.py app/schemas/skill.py app/schemas/mcp.py
git commit -m "feat(pools): assignment + tags fields on agent and pool schemas"
```

---

## Task 3: Read points — column-first id resolution

**Files:**
- Modify: `app/services/internal_agent.py`, `app/services/agent_executor.py`
- Modify: `tests/test_internal_agent.py`

- [ ] **Step 1: Write the failing precedence tests**

Add to `tests/test_internal_agent.py`:

```python
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
```

- [ ] **Step 2: Run, verify they FAIL**

Run: `docker compose exec -T api pip install -q pytest pytest-asyncio; docker compose exec -T api rm -rf /app/tests && docker cp tests cyberguard-api-1:/app/tests && docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_internal_agent.py -q -k 'prefers_assignment or falls_back_to_metadata'"`
Expected: FAIL (pool_tool_ids resolves from metadata, not the column).

- [ ] **Step 3: Update `InternalAgentRunner.__init__`**

In `app/services/internal_agent.py` `__init__`, change the id-source lines to prefer the columns with a metadata fallback:

```python
        self.associated_skills: List[int] = config.get("associated_skills") or []
        meta = config.get("metadata_json") or {}
        self.mcp_tool_ids: List[int] = config.get("associated_mcp_tools") or meta.get("mcp_tool_ids") or []
        self.pool_tool_ids: List[int] = config.get("associated_tools") or meta.get("tool_ids") or []
        self.permission_level: str = config.get("permission_level") or "medium"
```

(Keep the other `__init__` lines as they are. The `meta = config.get("metadata_json") or {}` line already exists — reuse it; don't duplicate.)

- [ ] **Step 4: Thread the columns through `agent_executor`**

In `app/services/agent_executor.py`, in `execute()` where `config_dict` is built, add after the `"associated_skills": agent_obj.associated_skills,` line:

```python
                "associated_tools": agent_obj.associated_tools,
                "associated_mcp_tools": agent_obj.associated_mcp_tools,
```

- [ ] **Step 5: Run, verify the precedence tests PASS**

Run: (re-copy tests) `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_internal_agent.py -q -k 'prefers_assignment or falls_back_to_metadata or dispatches_pool_tool or truncate or parallel or auto_continue or compact'"`
Expected: all selected pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/internal_agent.py app/services/agent_executor.py tests/test_internal_agent.py
git commit -m "feat(pools): internal agent reads assignment columns (metadata fallback)"
```

---

## Task 4: Pool API `?tag=` filter

**Files:**
- Modify: `app/routers/skills.py` (the `/skills` and `/tools` list routes)
- Modify: `app/routers/mcp.py` (the `/mcp/tools/all` route)

- [ ] **Step 1: Add the tag filter to `/skills` and `/tools`**

In `app/routers/skills.py`, the list routes currently look like
`async def list_skills(skip: int = 0, limit: int = 50, db: ..., _=...)`. Add a
`tag: Optional[str] = None` query param and filter in Python after fetch. For
`list_skills`:

```python
@router.get("/skills", response_model=SkillListResponse)
async def list_skills(skip: int = 0, limit: int = 50, tag: Optional[str] = None,
                      db: AsyncSession = Depends(get_db),
                      _=Depends(require_permission(Permission.SKILL_READ))):
    total_result = await db.execute(select(func.count(Skill.id)))
    total = total_result.scalar() or 0
    result = await db.execute(select(Skill).offset(skip).limit(limit))
    skills = result.scalars().all()
    if tag:
        skills = [s for s in skills if tag in (s.tags or [])]
    return SkillListResponse(total=total, skills=[SkillRead.model_validate(s) for s in skills])
```

Apply the same `tag` param + `if tag: tools = [t for t in tools if tag in (t.tags or [])]` filter to `list_tools`. (Keep the existing structure; only add the param, the filter line, and ensure `Optional` is imported in the file — it is used elsewhere.)

- [ ] **Step 2: Add the tag filter to `/mcp/tools/all`**

In `app/routers/mcp.py`, find the `/mcp/tools/all` route (around line 448). Add a `tag: Optional[str] = None` query param and filter its tool list in Python the same way (`if tag: tools = [t for t in tools if tag in (t.tags or [])]`) before building the response. Match the route's existing variable names (read it first).

- [ ] **Step 3: Live verify the filter end to end**

Run:
```bash
docker compose restart api && sleep 5
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
TID=$(curl -s -X POST http://localhost:8000/api/v1/tools -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"tagtest","command_template":"echo {m}","input_schema_json":"{\"type\":\"object\",\"properties\":{\"m\":{}}}","tags":["recon"]}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "with matching tag:"; curl -s "http://localhost:8000/api/v1/tools?tag=recon" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print([t['name'] for t in d['tools']])"
echo "with non-matching tag:"; curl -s "http://localhost:8000/api/v1/tools?tag=nope" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print([t['name'] for t in d['tools']])"
curl -s -X DELETE "http://localhost:8000/api/v1/tools/$TID" -H "Authorization: Bearer $TOKEN" -o /dev/null
```
Expected: first line includes `'tagtest'`; second line does NOT include it. Also confirms the create round-trips `tags`.

- [ ] **Step 4: Commit**

```bash
git add app/routers/skills.py app/routers/mcp.py
git commit -m "feat(pools): ?tag= filter on skills/tools/mcp-tools list endpoints"
```

---

## Task 5: WebUI — internal-agent assignment panel

**Files:**
- Modify: `webui/src/pages/Agents.tsx`
- Modify: `webui/src/api/client.ts` (confirm getSkills/getTools/getAllMcpTools exist)

- [ ] **Step 1: Confirm api client methods**

Run: `grep -n "getSkills\|getTools\|getAllMcpTools" webui/src/api/client.ts`
Expected: all three exist (getSkills, getTools, getAllMcpTools). If `getTools` is missing, add `getTools: () => request('/tools'),`.

- [ ] **Step 2: Load the three pools in Agents.tsx**

In `webui/src/pages/Agents.tsx`, add state + loading alongside the existing providers loading (the page already has `providers`/`loadProviders` from subproject ①). Add:

```tsx
  const [skillsPool, setSkillsPool] = useState<any[]>([])
  const [toolsPool, setToolsPool] = useState<any[]>([])
  const [mcpToolsPool, setMcpToolsPool] = useState<any[]>([])

  const loadPools = async () => {
    try {
      const s = await api.getSkills() as any
      setSkillsPool(Array.isArray(s) ? s : (s?.skills || []))
      const t = await api.getTools() as any
      setToolsPool(Array.isArray(t) ? t : (t?.tools || []))
      const m = await api.getAllMcpTools() as any
      setMcpToolsPool(Array.isArray(m) ? m : (m?.tools || []))
    } catch { /* leave pools empty */ }
  }
```

Call `loadPools()` in the existing mount `useEffect` (where `loadProviders()` is called).

- [ ] **Step 3: Add assignment state to the form**

The form state object (`form`) needs three id arrays. Add to the `FormState` interface and the initial/reset/openCreate/openEdit form objects:

```tsx
  associated_skills: number[]
  associated_tools: number[]
  associated_mcp_tools: number[]
```

Initialise them to `[]` everywhere `form` is constructed (initial `useState`, `openCreate`, and in `openEdit` populate from the agent: `associated_skills: a.associated_skills || []`, `associated_tools: a.associated_tools || []`, `associated_mcp_tools: a.associated_mcp_tools || []`). Add the matching optional fields to the `Agent` interface (`associated_tools?: number[]`, `associated_mcp_tools?: number[]`; `associated_skills?` may already exist — add if not).

- [ ] **Step 4: Render the pickers (internal kind only) and include in payload**

Inside the internal-agent fields block (where `form.backend_type === '__internal__'`), add a reusable multi-select. Add this helper component near the top of the file (module scope):

```tsx
function PoolPicker({ label, options, selected, onToggle }: {
  label: string
  options: { id: number; name?: string; tool_name?: string; tags?: string[]; version?: string }[]
  selected: number[]
  onToggle: (id: number) => void
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>{label}</label>
      <div style={{ maxHeight: 140, overflowY: 'auto', border: '1px solid var(--border-bright)', background: 'var(--bg-base)', padding: 8 }}>
        {options.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>— none —</div>}
        {options.map(o => {
          const name = o.name || o.tool_name || `#${o.id}`
          return (
            <label key={o.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={selected.includes(o.id)} onChange={() => onToggle(o.id)} />
              <span style={{ color: 'var(--text-primary)' }}>{name}</span>
              {o.version && <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>v{o.version}</span>}
              {o.tags && o.tags.length > 0 && <span style={{ fontSize: 11, color: '#60a5fa' }}>{o.tags.join(', ')}</span>}
            </label>
          )
        })}
      </div>
    </div>
  )
}
```

Add a toggle helper inside the component:

```tsx
  const toggleId = (key: 'associated_skills' | 'associated_tools' | 'associated_mcp_tools', id: number) =>
    setForm(f => ({ ...f, [key]: f[key].includes(id) ? f[key].filter(x => x !== id) : [...f[key], id] }))
```

Render the three pickers inside the internal-only block:

```tsx
<PoolPicker label="SKILLS" options={skillsPool} selected={form.associated_skills} onToggle={id => toggleId('associated_skills', id)} />
<PoolPicker label="TOOLS" options={toolsPool} selected={form.associated_tools} onToggle={id => toggleId('associated_tools', id)} />
<PoolPicker label="MCP TOOLS" options={mcpToolsPool} selected={form.associated_mcp_tools} onToggle={id => toggleId('associated_mcp_tools', id)} />
```

In `submit()`, in the internal branch, add the three lists to the payload:

```tsx
        payload.associated_skills = form.associated_skills
        payload.associated_tools = form.associated_tools
        payload.associated_mcp_tools = form.associated_mcp_tools
```

- [ ] **Step 5: Type-check, rebuild, verify**

Run: `cd webui && npx tsc --noEmit && echo TSC_OK`
Expected: `TSC_OK`.
Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && docker compose build webui && docker compose up -d webui`
Manual: create/edit an internal agent, tick a skill/tool/mcp tool, save, reopen → selections persist. (Backend round-trip is automatic via the columns.)

- [ ] **Step 6: Commit**

```bash
git add webui/src/pages/Agents.tsx webui/src/api/client.ts
git commit -m "feat(webui): internal-agent skill/tool/mcp assignment pickers"
```

---

## Task 6: WebUI — pool tags editor + filter + version

**Files:**
- Modify: `webui/src/pages/Tools.tsx`, `webui/src/pages/Skills.tsx`, `webui/src/pages/MCP.tsx`

- [ ] **Step 1: Add a tags input to each pool form**

In each of `Tools.tsx`, `Skills.tsx`, and `MCP.tsx` (the MCP tool form), add a tags field to the create/edit form. Store tags as a comma-separated string in form state and convert on submit. Add to the form markup (match each file's existing input styling):

```tsx
<label>TAGS (comma-separated)</label>
<input value={form.tagsText || ''}
  onChange={e => setForm(f => ({ ...f, tagsText: e.target.value }))}
  placeholder="recon, threat-intel" style={inputStyle} />
```

On submit, convert to an array in the payload:

```tsx
tags: (form.tagsText || '').split(',').map(s => s.trim()).filter(Boolean),
```

On edit, populate `tagsText` from the row: `tagsText: (row.tags || []).join(', ')`. Add `tagsText` to the form-state type and `tags?: string[]` to the item interface.

- [ ] **Step 2: Show tags + version on the list cards**

In each list item, render the tags and (for Skills/Tools) the version if present:

```tsx
{item.tags && item.tags.length > 0 && (
  <span style={{ fontSize: 11, color: '#60a5fa' }}>{item.tags.join(', ')}</span>
)}
{item.version && <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>v{item.version}</span>}
```

(MCP tools have no version — only render tags there.)

- [ ] **Step 3: Add a tag filter box to each list**

Add a `tagFilter` state and a small text input above each list; pass it to the list query. Simplest: keep client-side filtering OR call the API with `?tag=`. Use the API filter to match the backend:

```tsx
  const [tagFilter, setTagFilter] = useState('')
  // in the loader:
  const data = await api.getTools(tagFilter ? `?tag=${encodeURIComponent(tagFilter)}` : '') as any
```

If the existing `getTools`/`getSkills`/`getAllMcpTools` client methods don't accept a query suffix, extend them to take an optional string and append it (e.g. `getTools: (qs = '') => request('/tools' + qs)`), and re-run the loader when `tagFilter` changes (debounce not required; a "Filter" button or onBlur is fine). Add the input:

```tsx
<input value={tagFilter} onChange={e => setTagFilter(e.target.value)}
  onKeyDown={e => { if (e.key === 'Enter') load() }}
  placeholder="filter by tag…" style={inputStyle} />
```

- [ ] **Step 4: Type-check, rebuild, verify**

Run: `cd webui && npx tsc --noEmit && echo TSC_OK`
Expected: `TSC_OK`.
Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && docker compose build webui && docker compose up -d webui`
Manual: add tags to a tool, save, see them on the card; type a tag in the filter + Enter → list narrows; clear → full list.

- [ ] **Step 5: Commit**

```bash
git add webui/src/pages/Tools.tsx webui/src/pages/Skills.tsx webui/src/pages/MCP.tsx webui/src/api/client.ts
git commit -m "feat(webui): pool tags editor + tag filter + version display"
```

---

## Final verification

- [ ] `alembic current` → `012_pool_assignment_tags`; `associated_tools`/`associated_mcp_tools` on agent_configs; `tags` on skills/tools/mcp_tools.
- [ ] Precedence tests pass (columns win, metadata fallback works).
- [ ] Live: create internal agent with assigned skill/tool/mcp via WebUI → reopen shows the selections; `?tag=` filters a tagged tool.
- [ ] Internal agent run still dispatches assigned tools (the ① pool-tool path now fed by the column).
- [ ] Push the branch.

---

## Notes for the implementer

- Agent + pool CRUD persistence of the new fields is **automatic**: `create_agent`
  builds `AgentConfig(**{k:v for k,v in body_dict.items() if hasattr(AgentConfig,k)})`
  and `update_agent` uses `setattr`; pool create uses `Model(**body.model_dump())`.
  Once the model column + schema field exist, the value round-trips with no router
  change (except the `?tag=` filter in Task 4). Verify, don't re-implement.
- `_build_metadata` only handles `api_key` — it will not absorb the new columns.
- Do NOT touch `get_mcp_tools_for_agent` (external/OpenClaw delivery → subproject ③).
- DB-async test isolation issue persists; rely on the pure-logic precedence tests +
  live curl checks (as in subproject ①) rather than DB-backed pytest run together.
