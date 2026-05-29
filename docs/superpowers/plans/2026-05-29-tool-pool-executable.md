# Executable Tool Pool (subproject ①) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the doc-only `Tool` pool into executable, parameterised host-tool commands run in an isolated `tool-runner` container, wired into the internal agent.

**Architecture:** `Tool` gains `command_template` + `input_schema_json`. `app/services/tool_executor.py` validates args, builds an injection-safe argv (shlex-split template, placeholders → single argv tokens, no shell), gates on RBAC + high-permission approval, and POSTs the argv to a new `tool-runner` FastAPI container that runs it via `create_subprocess_exec`. The internal agent calls Tools as callable tools via a temporary `metadata_json.tool_ids`.

**Tech Stack:** FastAPI, SQLAlchemy (async) + Alembic, httpx, asyncio subprocess, pytest/pytest-asyncio, React/TS WebUI. Spec: `docs/superpowers/specs/2026-05-29-tool-pool-executable-design.md`.

---

## File structure

- `app/models/skill.py` — add columns to `Tool` (modify).
- `alembic/versions/011_tool_executable.py` — migration (create).
- `app/schemas/skill.py` — `Tool*` schemas gain executable fields (modify).
- `app/services/tool_executor.py` — argv builder + `execute_tool` (create).
- `tool_runner/main.py` — runner FastAPI app (create).
- `tool-runner/Dockerfile` — runner image (create).
- `docker-compose.yml` — add `tool-runner` service + api env (modify).
- `app/routers/skills.py` — add `POST /tools/{id}/execute` (modify).
- `app/services/internal_agent.py` — Tool catalogue + dispatch (modify).
- `tests/test_tool_executor.py` — pure-logic + service tests (create).
- `tests/test_internal_agent.py` — Tool dispatch test (modify).
- `webui/src/pages/Skills.tsx` — Tool form + TEST button (modify; confirm path in Task 8).

---

## Task 1: `Tool` model — executable columns

**Files:**
- Modify: `app/models/skill.py` (the `Tool` class)
- Create: `alembic/versions/011_tool_executable.py`

- [ ] **Step 1: Add columns to the `Tool` model**

In `app/models/skill.py`, inside `class Tool(Base)`, after the `md_content` line change `md_content` to nullable and add the executable columns:

```python
    md_content = Column(Text, nullable=True)  # now optional human notes/docs
    command_template = Column(Text, nullable=True)  # e.g. "nmap -sV -p {ports} {target}"
    input_schema_json = Column(Text, nullable=True)  # JSON Schema for params
    timeout_seconds = Column(Integer, default=60, nullable=False)
    required_permission = Column(String(100), nullable=True, index=True)
```

- [ ] **Step 2: Write the migration**

Create `alembic/versions/011_tool_executable.py`:

```python
"""tool pool executable columns

Revision ID: 011_tool_executable
Revises: 010_agent_kind_and_internal
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "011_tool_executable"
down_revision = "010_agent_kind_and_internal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("command_template", sa.Text(), nullable=True))
    op.add_column("tools", sa.Column("input_schema_json", sa.Text(), nullable=True))
    op.add_column("tools", sa.Column("timeout_seconds", sa.Integer(),
                                     nullable=False, server_default="60"))
    op.add_column("tools", sa.Column("required_permission", sa.String(100), nullable=True))
    op.create_index("ix_tools_required_permission", "tools", ["required_permission"])
    op.alter_column("tools", "md_content", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("tools", "md_content", existing_type=sa.Text(), nullable=False)
    op.drop_index("ix_tools_required_permission", table_name="tools")
    op.drop_column("tools", "required_permission")
    op.drop_column("tools", "timeout_seconds")
    op.drop_column("tools", "input_schema_json")
    op.drop_column("tools", "command_template")
```

- [ ] **Step 3: Apply the migration**

Run: `docker compose exec -T api alembic upgrade head`
Expected: ends at `011_tool_executable`. Verify:
Run: `docker compose exec -T postgres psql -U postgres -d cyberguard -c "\d tools" | grep command_template`
Expected: shows `command_template | text`.

- [ ] **Step 4: Commit**

```bash
git add app/models/skill.py alembic/versions/011_tool_executable.py
git commit -m "feat(tools): executable columns on Tool model + migration 011"
```

---

## Task 2: `Tool` schemas — executable fields

**Files:**
- Modify: `app/schemas/skill.py` (`ToolBase`, `ToolCreate`, `ToolUpdate`, `ToolResponse`)

- [ ] **Step 1: Add executable fields to the schemas**

In `app/schemas/skill.py`, update the Tool schemas. Add to `ToolBase`:

```python
class ToolBase(BaseModel):
    """Base tool schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    permission_level: str = "medium"
    requires_approval: bool = False
    is_active: bool = True
    command_template: Optional[str] = None
    input_schema_json: Optional[str] = None
    timeout_seconds: int = 60
    required_permission: Optional[str] = None
```

Change `ToolCreate.md_content` to optional and keep version/metadata:

```python
class ToolCreate(ToolBase):
    """Tool creation schema."""
    md_content: Optional[str] = None
    version: str = "1.0.0"
    metadata_json: Optional[Dict[str, Any]] = None
```

Add the same optional fields to `ToolUpdate`:

```python
    command_template: Optional[str] = None
    input_schema_json: Optional[str] = None
    timeout_seconds: Optional[int] = None
    required_permission: Optional[str] = None
```

Add to `ToolResponse` (after `metadata_json`):

```python
    command_template: Optional[str] = None
    input_schema_json: Optional[str] = None
    timeout_seconds: int = 60
    required_permission: Optional[str] = None
```

- [ ] **Step 2: Smoke-check import**

Run: `docker compose exec -T api python -c "from app.schemas.skill import ToolCreate, ToolResponse; print(ToolCreate(name='t', command_template='echo {m}').timeout_seconds)"`
Expected: prints `60`.

- [ ] **Step 3: Commit**

```bash
git add app/schemas/skill.py
git commit -m "feat(tools): executable fields on Tool schemas"
```

---

## Task 3: argv builder + arg validation (pure logic, TDD)

**Files:**
- Create: `app/services/tool_executor.py`
- Create: `tests/test_tool_executor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tool_executor.py`:

```python
import pytest
from app.services.tool_executor import build_argv, ToolArgError


SCHEMA = {"type": "object",
          "properties": {"ports": {"type": "string"}, "target": {"type": "string"}},
          "required": ["target"]}


def test_build_argv_fills_placeholders_as_single_tokens():
    argv = build_argv("nmap -sV -p {ports} {target}", SCHEMA,
                      {"ports": "80,443", "target": "example.com"})
    assert argv == ["nmap", "-sV", "-p", "80,443", "example.com"]


def test_build_argv_arg_with_spaces_stays_one_token():
    argv = build_argv("echo {msg}", {"type": "object",
                      "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
                      {"msg": "hello world; rm -rf /"})
    # the whole malicious string is ONE argv element, never shell-parsed
    assert argv == ["echo", "hello world; rm -rf /"]


def test_build_argv_rejects_unknown_key():
    with pytest.raises(ToolArgError):
        build_argv("echo {msg}", {"type": "object",
                   "properties": {"msg": {}}, "required": []}, {"bogus": "x"})


def test_build_argv_rejects_missing_required():
    with pytest.raises(ToolArgError):
        build_argv("nmap {target}", SCHEMA, {"ports": "80"})


def test_build_argv_rejects_unfilled_placeholder():
    with pytest.raises(ToolArgError):
        build_argv("nmap {target} {ports}", SCHEMA, {"target": "x"})


def test_build_argv_rejects_embedded_placeholder():
    # placeholder not a standalone token (would allow injection of flags)
    with pytest.raises(ToolArgError):
        build_argv("nmap -p{ports}", SCHEMA, {"ports": "80", "target": "x"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_tool_executor.py -q"` (copy tests first via `docker cp tests cyberguard-api-1:/app/tests` after `docker compose exec -T api rm -rf /app/tests`)
Expected: FAIL with `ModuleNotFoundError: app.services.tool_executor`.

- [ ] **Step 3: Implement the argv builder**

Create `app/services/tool_executor.py`:

```python
"""Executable Tool pool — validate args, build an injection-safe argv, and run
it in the isolated tool-runner container. See:
  docs/superpowers/specs/2026-05-29-tool-pool-executable-design.md
"""
import json
import os
import shlex
from typing import Any, Dict, List, Optional

import httpx


TOOL_RUNNER_URL = os.environ.get("TOOL_RUNNER_URL", "http://tool-runner:9000")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
OUTPUT_MAX_CHARS = 8000  # mirror internal_agent.TOOL_RESULT_MAX_CHARS


class ToolArgError(ValueError):
    """Raised when supplied args don't satisfy the tool's input schema/template."""


def build_argv(command_template: str, input_schema: Optional[Dict[str, Any]],
               args: Dict[str, Any]) -> List[str]:
    """Turn a command template + args into a safe argv list.

    Placeholders must be standalone `{name}` tokens whose name is declared in the
    schema's properties; each becomes a single argv element (never shell-parsed),
    making command injection structurally impossible.
    """
    schema = input_schema or {}
    props = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []

    for k in args:
        if k not in props:
            raise ToolArgError(f"unknown argument: {k!r}")
    for k in required:
        if k not in args:
            raise ToolArgError(f"missing required argument: {k!r}")

    if not command_template:
        raise ToolArgError("tool has no command_template")

    argv: List[str] = []
    for tok in shlex.split(command_template):
        if len(tok) >= 2 and tok[0] == "{" and tok[-1] == "}":
            name = tok[1:-1]
            if name not in props:
                raise ToolArgError(f"placeholder {tok} not in schema")
            if name not in args:
                raise ToolArgError(f"unfilled placeholder: {name!r}")
            argv.append(str(args[name]))
        elif "{" in tok or "}" in tok:
            raise ToolArgError(f"placeholder must be a standalone token, got {tok!r}")
        else:
            argv.append(tok)
    return argv
```

- [ ] **Step 4: Run tests to verify they pass**

Run: (re-copy tests) `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_tool_executor.py -q"`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_tool_executor.py
git commit -m "feat(tools): injection-safe argv builder (TDD)"
```

---

## Task 4: `execute_tool` service (validate → gate → dispatch)

**Files:**
- Modify: `app/services/tool_executor.py`
- Modify: `tests/test_tool_executor.py`

- [ ] **Step 1: Write the failing tests (mock the runner + approval)**

Append to `tests/test_tool_executor.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _tool(**kw):
    base = dict(command_template="echo {msg}",
                input_schema_json=json.dumps({"type": "object",
                    "properties": {"msg": {"type": "string"}}, "required": ["msg"]}),
                timeout_seconds=30, permission_level="medium", required_permission=None)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_execute_tool_dispatches_to_runner():
    from app.services import tool_executor as te
    fake_resp = SimpleNamespace(status_code=200, json=lambda: {
        "stdout": "hi", "stderr": "", "exit_code": 0, "duration_ms": 5, "timed_out": False})
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(return_value=fake_resp)
    with patch.object(te.httpx, "AsyncClient", return_value=client):
        res = await te.execute_tool(_tool(), {"msg": "hi"}, user_id=1)
    assert res["status"] == "completed"
    assert res["stdout"] == "hi"


@pytest.mark.asyncio
async def test_execute_tool_high_permission_needs_approval():
    from app.services import tool_executor as te
    with patch.object(te, "_create_approval", AsyncMock()):
        res = await te.execute_tool(_tool(permission_level="high"), {"msg": "x"}, user_id=1)
    assert res["status"] == "needs_approval"


@pytest.mark.asyncio
async def test_execute_tool_rejects_bad_args():
    from app.services import tool_executor as te
    res = await te.execute_tool(_tool(), {"bogus": "x"}, user_id=1)
    assert res["status"] == "error"
    assert "unknown argument" in res["error"]


@pytest.mark.asyncio
async def test_execute_tool_rbac_denied():
    from app.services import tool_executor as te
    res = await te.execute_tool(_tool(required_permission="tool:exec"),
                                {"msg": "x"}, user_id=1, caller_permissions=set())
    assert res["status"] == "error"
    assert "permission" in res["error"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: (re-copy tests) `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_tool_executor.py -q -k execute_tool"`
Expected: FAIL with `AttributeError: ... execute_tool`.

- [ ] **Step 3: Implement `execute_tool` + `_create_approval`**

Append to `app/services/tool_executor.py`:

```python
import uuid


def _truncate(text: str) -> str:
    if text and len(text) > OUTPUT_MAX_CHARS:
        return text[:OUTPUT_MAX_CHARS] + f"\n…[truncated {len(text) - OUTPUT_MAX_CHARS} chars]"
    return text or ""


async def _create_approval(tool, args: Dict[str, Any], user_id: int) -> None:
    from app.services.approval_service import ApprovalService
    await ApprovalService().create_request(
        request_id=str(uuid.uuid4()),
        user_id=user_id,
        action_type="tool.execute",
        action_description=f"Execute tool {getattr(tool, 'name', '?')}",
        payload={"tool": getattr(tool, "name", None), "args": args},
        risk_level="high",
    )


async def execute_tool(tool, args: Dict[str, Any], user_id: int, *,
                       approved: bool = False,
                       caller_permissions: Optional[set] = None) -> Dict[str, Any]:
    """Validate args, gate on RBAC/approval, run in the tool-runner. JSON-safe result."""
    # RBAC: only enforced when caller_permissions is provided (API path). The
    # internal-agent path passes None — assignment to the agent is the authorization.
    req = getattr(tool, "required_permission", None)
    if req and caller_permissions is not None and req not in caller_permissions:
        return {"status": "error", "error": f"missing required permission: {req}"}

    # Approval gate for high-permission tools.
    if getattr(tool, "permission_level", "medium") == "high" and not approved:
        await _create_approval(tool, args, user_id)
        return {"status": "needs_approval",
                "error": "High-permission tool requires approval"}

    try:
        schema = json.loads(tool.input_schema_json) if tool.input_schema_json else {}
    except json.JSONDecodeError:
        schema = {}
    try:
        argv = build_argv(tool.command_template or "", schema, args)
    except ToolArgError as e:
        return {"status": "error", "error": str(e)}

    timeout = int(getattr(tool, "timeout_seconds", 60) or 60)
    try:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            r = await client.post(
                f"{TOOL_RUNNER_URL}/run",
                json={"argv": argv, "timeout": timeout},
                headers={"X-Runner-Token": RUNNER_TOKEN},
            )
    except Exception as e:
        return {"status": "error", "error": f"tool-runner unreachable: {e}"}

    if r.status_code != 200:
        return {"status": "error", "error": f"tool-runner {r.status_code}: {r.text[:200]}"}
    data = r.json()
    return {
        "status": "completed",
        "stdout": _truncate(data.get("stdout", "")),
        "stderr": _truncate(data.get("stderr", "")),
        "exit_code": data.get("exit_code"),
        "duration_ms": data.get("duration_ms"),
        "timed_out": data.get("timed_out", False),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: (re-copy tests) `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_tool_executor.py -q"`
Expected: all pass (6 builder + 4 service = 10).

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_tool_executor.py
git commit -m "feat(tools): execute_tool with RBAC + approval gate + runner dispatch"
```

---

## Task 5: `tool-runner` container

**Files:**
- Create: `tool_runner/main.py`
- Create: `tool-runner/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Write the runner app**

Create `tool_runner/main.py`:

```python
"""Isolated tool-runner: executes a given argv with no shell. Driven only by api."""
import asyncio
import os
import time

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="tool-runner")

RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
OUTPUT_MAX_BYTES = 64_000


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run")
async def run(body: dict, x_runner_token: str = Header(default="")):
    if RUNNER_TOKEN and x_runner_token != RUNNER_TOKEN:
        raise HTTPException(status_code=401, detail="bad runner token")
    argv = body.get("argv") or []
    timeout = int(body.get("timeout") or 60)
    if not argv or not isinstance(argv, list):
        raise HTTPException(status_code=400, detail="argv must be a non-empty list")

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"command not found: {argv[0]}",
                "exit_code": 127, "duration_ms": 0, "timed_out": False}

    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        out, err = await proc.communicate()
        timed_out = True
    return {
        "stdout": (out or b"").decode("utf-8", "replace")[:OUTPUT_MAX_BYTES],
        "stderr": (err or b"").decode("utf-8", "replace")[:OUTPUT_MAX_BYTES],
        "exit_code": proc.returncode,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "timed_out": timed_out,
    }
```

- [ ] **Step 2: Write the runner Dockerfile**

Create `tool-runner/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Runner deps only (kept minimal; add security tools below as needed).
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

# --- Security tools layer (extend this list as your team needs) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
    && rm -rf /var/lib/apt/lists/*

COPY tool_runner/ ./tool_runner/

EXPOSE 9000
CMD ["uvicorn", "tool_runner.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

- [ ] **Step 3: Add the service + api env to docker-compose**

In `docker-compose.yml`, add to the `api` service `environment:` block:

```yaml
      TOOL_RUNNER_URL: http://tool-runner:9000
      RUNNER_TOKEN: ${RUNNER_TOKEN:-changeme-runner-token}
```

And add a new service (place near the other services, same indentation level):

```yaml
  tool-runner:
    build:
      context: .
      dockerfile: tool-runner/Dockerfile
    environment:
      RUNNER_TOKEN: ${RUNNER_TOKEN:-changeme-runner-token}
    # No host port: only reachable on the compose network as tool-runner:9000.
    restart: unless-stopped
```

- [ ] **Step 4: Build, start, and smoke-test the runner**

Run:
```bash
docker compose build tool-runner && docker compose up -d tool-runner
docker compose exec -T api python -c "
import asyncio, os, httpx
async def go():
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post('http://tool-runner:9000/run',
            json={'argv':['echo','hello'],'timeout':5},
            headers={'X-Runner-Token': os.environ.get('RUNNER_TOKEN','changeme-runner-token')})
        print(r.json())
asyncio.run(go())
"
```
Expected: prints `{'stdout': 'hello\n', 'stderr': '', 'exit_code': 0, ...}`.

- [ ] **Step 5: Commit**

```bash
git add tool_runner/main.py tool-runner/Dockerfile docker-compose.yml
git commit -m "feat(tools): isolated tool-runner container + api wiring"
```

---

## Task 6: Standalone execute API endpoint

**Files:**
- Modify: `app/routers/skills.py`

- [ ] **Step 1: Add the execute endpoint**

In `app/routers/skills.py`, add near the other `/tools` routes. First ensure imports at top include the executor and current-user dependency:

```python
from app.services.tool_executor import execute_tool
from app.core.dependencies import get_current_user  # confirm this exists; it backs require_permission
from app.core.rbac import ROLE_PERMISSIONS
```

Then add:

```python
@router.post("/tools/{tool_id}/execute")
async def execute_pool_tool(
    tool_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """Run an executable Tool with the supplied args (manual test / direct call)."""
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if not tool.command_template:
        raise HTTPException(status_code=400, detail="Tool is not executable (no command_template)")
    # Resolve the caller's permission set from their role for required_permission RBAC.
    perms = {p.value for p in ROLE_PERMISSIONS.get(current_user.role, [])}
    return await execute_tool(
        tool, body.get("args") or {}, user_id=current_user.id,
        caller_permissions=perms,
    )
```

- [ ] **Step 2: Verify `get_current_user` and `ROLE_PERMISSIONS` exist**

Run: `docker compose exec -T api python -c "from app.core.dependencies import get_current_user; from app.core.rbac import ROLE_PERMISSIONS; print('ok')"`
Expected: prints `ok`. If `get_current_user` is named differently, grep `app/core/dependencies.py` for the user dependency and use that name in Step 1.

- [ ] **Step 3: End-to-end manual test via the API**

Run:
```bash
docker compose restart api && sleep 5
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
TID=$(curl -s -X POST http://localhost:8000/api/v1/tools -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"echo_test","command_template":"echo {msg}","input_schema_json":"{\"type\":\"object\",\"properties\":{\"msg\":{\"type\":\"string\"}},\"required\":[\"msg\"]}","permission_level":"low"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST "http://localhost:8000/api/v1/tools/$TID/execute" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"args":{"msg":"hello-from-tool"}}'
echo
curl -s -X DELETE "http://localhost:8000/api/v1/tools/$TID" -H "Authorization: Bearer $TOKEN" -o /dev/null
```
Expected: JSON `{"status":"completed","stdout":"hello-from-tool\n","exit_code":0,...}`.

- [ ] **Step 4: Commit**

```bash
git add app/routers/skills.py
git commit -m "feat(tools): POST /tools/{id}/execute endpoint with RBAC"
```

---

## Task 7: Internal agent wiring (temporary `metadata_json.tool_ids`)

**Files:**
- Modify: `app/services/internal_agent.py`
- Modify: `tests/test_internal_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_internal_agent.py`:

```python
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

    # Stub the pool-tool catalogue + executor.
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: (re-copy tests) `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_internal_agent.py -q -k dispatches_pool_tool"`
Expected: FAIL (`_load_pool_tools` / pool tool not handled).

- [ ] **Step 3: Implement pool-tool catalogue + dispatch**

In `app/services/internal_agent.py`:

(a) Add import near the top:

```python
from app.services.tool_executor import execute_tool
```

(b) In `__init__`, read the temporary tool_ids alongside mcp_tool_ids:

```python
        self.pool_tool_ids: List[int] = meta.get("tool_ids") or []
```

(c) Add a loader method (place next to `_load_mcp_tools`):

```python
    async def _load_pool_tools(self):
        """Load executable Tool-pool rows referenced by metadata_json.tool_ids."""
        if not self.pool_tool_ids:
            return []
        from app.models.skill import Tool
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Tool).where(Tool.id.in_(self.pool_tool_ids),
                                   Tool.is_active == True,
                                   Tool.command_template.isnot(None))
            )
            return list(result.scalars().all())
```

(d) In `_build_tools`, after MCP tools and before the kb tool, append pool tools and remember them for dispatch (MCP names win on collision):

```python
        self._pool_tools_by_name = {}
        mcp_names = {t["function"]["name"] for t in tools}
        for pt in await self._load_pool_tools():
            if pt.name in mcp_names:
                continue  # MCP name wins; skip colliding pool tool
            try:
                schema = json.loads(pt.input_schema_json) if pt.input_schema_json else {}
            except json.JSONDecodeError:
                schema = {}
            if not isinstance(schema, dict):
                schema = {}
            self._pool_tools_by_name[pt.name] = pt
            tools.append({
                "type": "function",
                "function": {
                    "name": pt.name,
                    "description": pt.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            })
```

(Initialise `self._pool_tools_by_name = {}` at the start of `_build_tools` so it exists even when there are no pool tools.)

(e) In `_dispatch`, add a branch before the final `unknown tool` return:

```python
        # 3. Executable pool Tool
        if getattr(self, "_pool_tools_by_name", None) and name in self._pool_tools_by_name:
            tool_row = self._pool_tools_by_name[name]
            if (tool_row.permission_level or "medium") == "high":
                return f"ERROR: tool {name!r} requires approval (high permission)"
            res = await execute_tool(tool_row, args, user_id=getattr(self, "_user_id", 0))
            if res.get("status") == "completed":
                return res.get("stdout", "") or "(no output)"
            return f"ERROR: tool {name!r}: {res.get('error') or res.get('stderr') or res}"
```

(f) In `execute`, capture `user_id` so `_dispatch` can pass it. Right after the method signature body starts (e.g. after `start = time.monotonic()`), add:

```python
        self._user_id = user_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: (re-copy tests) `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_internal_agent.py -q -k 'dispatches_pool_tool or truncate or parallel or auto_continue or compact'"`
Expected: all selected pass (the pure-logic + new pool-tool test).

- [ ] **Step 5: Commit**

```bash
git add app/services/internal_agent.py tests/test_internal_agent.py
git commit -m "feat(tools): internal agent calls executable pool Tools (temp tool_ids)"
```

---

## Task 8: WebUI — Tool form + TEST button

**Files:**
- Modify: `webui/src/pages/Skills.tsx` (confirm the Tool UI lives here in Step 1)
- Modify: `webui/src/api/client.ts` (add `executeTool`)

- [ ] **Step 1: Locate the Tool form**

Run: `grep -rn "tools\|Tool\|md_content" webui/src/pages/Skills.tsx | head`
Expected: confirms the Tool create/edit form fields. If Tools live in a different file, grep `webui/src` for the Tool form and use that path for the rest of this task.

- [ ] **Step 2: Add the API client method**

In `webui/src/api/client.ts`, near the other tool calls, add:

```typescript
  executeTool: (id: number, args: Record<string, any>) =>
    request(`/tools/${id}/execute`, { method: 'POST', body: JSON.stringify({ args }) }),
```

- [ ] **Step 3: Add executable fields to the Tool form**

In the Tool form component, add inputs bound to the form state for:
`command_template` (text input, placeholder `nmap -sV -p {ports} {target}`),
`input_schema_json` (textarea, JSON Schema),
`timeout_seconds` (number, default 60),
`required_permission` (text, optional),
and make the existing `md_content` field optional (label it "Notes (optional)").
Include these keys in the create/update payload sent to `POST/PUT /tools`.

```tsx
<label>COMMAND TEMPLATE</label>
<input value={form.command_template || ''}
  onChange={e => setForm(f => ({ ...f, command_template: e.target.value }))}
  placeholder="nmap -sV -p {ports} {target}" style={inputStyle} />

<label>INPUT SCHEMA (JSON)</label>
<textarea value={form.input_schema_json || ''}
  onChange={e => setForm(f => ({ ...f, input_schema_json: e.target.value }))}
  placeholder='{"type":"object","properties":{"target":{"type":"string"}},"required":["target"]}'
  rows={4} style={{ ...inputStyle, height: 'auto' }} />

<label>TIMEOUT (s)</label>
<input type="number" value={form.timeout_seconds ?? 60}
  onChange={e => setForm(f => ({ ...f, timeout_seconds: parseInt(e.target.value || '60', 10) }))}
  style={inputStyle} />

<label>REQUIRED PERMISSION (optional)</label>
<input value={form.required_permission || ''}
  onChange={e => setForm(f => ({ ...f, required_permission: e.target.value }))}
  placeholder="tool:exec" style={inputStyle} />
```

- [ ] **Step 4: Add an EXECUTABLE badge + TEST action to the Tool list**

In the Tool list item, when `tool.command_template` is set, show a badge and a TEST button that prompts for JSON args and calls `executeTool`:

```tsx
{tool.command_template && (
  <>
    <span style={{ fontSize: 11, color: '#60a5fa' }}>EXECUTABLE</span>
    <button onClick={async () => {
      const raw = prompt(`Args JSON for ${tool.name}:`, '{}')
      if (raw == null) return
      try {
        const res = await api.executeTool(tool.id, JSON.parse(raw))
        alert(`status: ${res.status}\nexit: ${res.exit_code}\n\n${res.stdout || res.error || ''}`)
      } catch (e: any) { alert(e.message) }
    }}>TEST</button>
  </>
)}
```

- [ ] **Step 5: Type-check, rebuild, verify**

Run: `cd webui && npx tsc --noEmit && echo TSC_OK`
Expected: `TSC_OK`.
Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && docker compose build webui && docker compose up -d webui`
Then in the app: open the Tool pool, create an executable tool (`echo {msg}`), click TEST with `{"msg":"hi"}`, confirm stdout `hi` is shown.

- [ ] **Step 6: Commit**

```bash
git add webui/src/pages/Skills.tsx webui/src/api/client.ts
git commit -m "feat(webui): executable Tool form + TEST button"
```

---

## Final verification

- [ ] Run the pure-logic + service tests: `docker compose exec -T api sh -c "cd /app && python -m pytest tests/test_tool_executor.py -q"` → all pass.
- [ ] Run the internal-agent pool-tool + logic tests (selected) → pass.
- [ ] Manual: create an executable Tool, attach to an internal agent via `metadata_json.tool_ids`, run a chat that uses it, confirm the tool output flows back.
- [ ] Push the branch.

---

## Notes for the implementer

- **Test harness:** the api container has no pytest by default. Install once:
  `docker compose exec -T api pip install -q pytest pytest-asyncio`. Tests aren't
  mounted — copy them in before each run: `docker compose exec -T api rm -rf /app/tests && docker cp tests cyberguard-api-1:/app/tests`.
- **DB-async test isolation:** the known pytest-asyncio "event loop is closed"
  issue (see `project_status.md`) affects DB-backed tests when run together. The
  `tool_executor` tests and the internal-agent pool-tool test are mock-based /
  pure-logic and unaffected; run them with `-k` selectors as shown.
- **Set `RUNNER_TOKEN`** in your `.env` to a real secret before production; the
  compose default `changeme-runner-token` is for local only.
- **Adding tools to the runner:** extend the apt-get line in `tool-runner/Dockerfile`
  and rebuild `tool-runner`.
