# Safety Envelope & Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Standard's Safety Envelope control (B6) — every `contain_soft` / `contain_hard` / `remediate` action must have pre-action validation, post-action verification, and a registered rollback procedure; if rollback fails, page on-call.

**Architecture:** Because CyberGuard is multi-worker and runs actions as argv in an isolated tool-runner, rollbacks are **declarative commands**, not in-process Python closures. Executable tools gain optional `validation_command_template`, `verification_command_template`, and `rollback_command_template`. A durable `rollback_registry` (DB table) records `action_id → rollback argv + TTL`. The gatekeeper **denies** an envelope-requiring action whose tool has no rollback. `execute_tool()` runs pre-validation, then on success registers the rollback (and optionally runs post-verification, auto-reverting + paging on failure). A `POST /governance/rollback/{action_id}` endpoint executes a revert.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, httpx → tool-runner, `webhook_service.emit` / `email_service` for paging, pytest. Naive-UTC timestamps.

---

## Dependencies & decisions

- **Depends on prior plans:** reuses `app/services/gatekeeper.py` (Phase-2 of `2026-06-09-agent-governance-controls.md`), the `action_category` tool column, and `execute_tool()` wiring. Migrations chain on top of `027_approval_approver_role` (governance-config plan) → `028` → `029`. Land plans 1–2 first.
- **Envelope categories:** `contain_soft`, `contain_hard`, `remediate` (Standard §Safety Envelope). `observe`/`annotate`/`notify`/`mutate` are out of scope here (`mutate` is already forbidden in POC by the gatekeeper).
- **Rollback is declarative:** stored as a tool-runner argv computed from `rollback_command_template` + the original action args. No persisted Python closures (won't survive workers/restarts).
- **TTL default 3600s** (matches the Standard's example). Expired registrations are not auto-executed.
- **"Page on-call":** `webhook_service.emit("rollback.failed", {...})` + best-effort `email_service.send_email` to the configured on-call address. Reuses existing egress; no new pager integration.
- **Scope:** the executable **Tool pool** (`tools`, which have `command_template`). MCP tools (server-mediated) are a follow-up — flagged in self-review.

## File Structure

| File | Responsibility |
|------|----------------|
| `app/models/skill.py` (modify) | `validation_/verification_/rollback_command_template` on `Tool` |
| `alembic/versions/028_tool_safety_envelope.py` (create) | Migrate the 3 tool columns |
| `app/models/rollback.py` (create) | `RollbackRegistration` table |
| `alembic/versions/029_rollback_registry.py` (create) | Migrate the registry table |
| `app/services/safety_envelope.py` (create) | `requires_envelope`, `has_rollback`, `register_rollback`, `execute_rollback`, `run_command` |
| `app/services/gatekeeper.py` (modify) | Deny envelope action with no rollback |
| `app/services/tool_executor.py` (modify) | Pre-validate + register rollback on success |
| `app/routers/governance_rollback.py` (create) | `POST /governance/rollback/{action_id}`, `GET /governance/rollback` |
| `app/main.py` (modify) | Register the router |
| `tests/test_safety_envelope.py` (create) | Service + gatekeeper + revert/paging tests |

---

### Task 1: Tool safety-envelope columns

**Files:**
- Modify: `app/models/skill.py`
- Create: `alembic/versions/028_tool_safety_envelope.py`

- [ ] **Step 1: Add columns to `Tool`** (after the `action_category`/`risk_tier` columns added by the prior plan):

```python
    validation_command_template = Column(Text, nullable=True)    # pre-action dry-run/sim
    verification_command_template = Column(Text, nullable=True)  # post-action health check
    rollback_command_template = Column(Text, nullable=True)      # revert command
```

- [ ] **Step 2: Migration `028_tool_safety_envelope.py`** (head is `027_approval_approver_role`)

```python
"""tools: safety-envelope command templates (validation/verification/rollback)

Revision ID: 028_tool_safety_envelope
Revises: 027_approval_approver_role
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "028_tool_safety_envelope"
down_revision = "027_approval_approver_role"
branch_labels = None
depends_on = None

_COLS = ("validation_command_template", "verification_command_template", "rollback_command_template")


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tools")}


def upgrade() -> None:
    existing = _existing()
    for c in _COLS:
        if c not in existing:
            op.add_column("tools", sa.Column(c, sa.Text(), nullable=True))


def downgrade() -> None:
    existing = _existing()
    for c in reversed(_COLS):
        if c in existing:
            op.drop_column("tools", c)
```

- [ ] **Step 3: Migrate + commit**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
git add app/models/skill.py alembic/versions/028_tool_safety_envelope.py
git commit -m "feat(envelope): safety-envelope command templates on tools"
```

### Task 2: Rollback registry table

**Files:**
- Create: `app/models/rollback.py`, `alembic/versions/029_rollback_registry.py`

- [ ] **Step 1: Model**

```python
# app/models/rollback.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.core.database import Base


class RollbackRegistration(Base):
    __tablename__ = "rollback_registrations"
    id = Column(Integer, primary_key=True, index=True)
    action_id = Column(String(36), unique=True, nullable=False, index=True)
    tool_id = Column(Integer, nullable=True)
    tool_name = Column(String(100), nullable=True)
    rollback_argv = Column(JSON, nullable=False)        # list[str] for the tool-runner
    status = Column(String(20), nullable=False, default="registered")  # registered|reverted|failed|expired
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    reverted_at = Column(DateTime, nullable=True)
    detail = Column(String(500), nullable=True)
```

- [ ] **Step 2: Migration `029_rollback_registry.py`**

```python
"""rollback_registrations table (Safety Envelope)

Revision ID: 029_rollback_registry
Revises: 028_tool_safety_envelope
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "029_rollback_registry"
down_revision = "028_tool_safety_envelope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "rollback_registrations" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "rollback_registrations",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("action_id", sa.String(36), nullable=False, unique=True),
            sa.Column("tool_id", sa.Integer, nullable=True),
            sa.Column("tool_name", sa.String(100), nullable=True),
            sa.Column("rollback_argv", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("reverted_at", sa.DateTime, nullable=True),
            sa.Column("detail", sa.String(500), nullable=True),
        )
        op.create_index("ix_rollback_action_id", "rollback_registrations", ["action_id"])
        op.create_index("ix_rollback_expires_at", "rollback_registrations", ["expires_at"])


def downgrade() -> None:
    if "rollback_registrations" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_rollback_expires_at", table_name="rollback_registrations")
        op.drop_index("ix_rollback_action_id", table_name="rollback_registrations")
        op.drop_table("rollback_registrations")
```

- [ ] **Step 3: Migrate + commit**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
git add app/models/rollback.py alembic/versions/029_rollback_registry.py
git commit -m "feat(envelope): rollback_registrations table + migration 029"
```

### Task 3: Safety-envelope service

**Files:**
- Create: `app/services/safety_envelope.py`
- Test: `tests/test_safety_envelope.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_safety_envelope.py
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services import safety_envelope as se


def _tool(**kw):
    base = dict(id=1, name="isolator", action_category="contain_hard",
                input_schema_json=json.dumps({"type": "object",
                    "properties": {"host": {"type": "string"}}, "required": ["host"]}),
                rollback_command_template="unisolate {host}",
                validation_command_template=None, verification_command_template=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_requires_envelope():
    assert se.requires_envelope("contain_hard") is True
    assert se.requires_envelope("remediate") is True
    assert se.requires_envelope("observe") is False


def test_has_rollback():
    assert se.has_rollback(_tool()) is True
    assert se.has_rollback(_tool(rollback_command_template=None)) is False


@pytest.mark.asyncio
async def test_register_rollback_persists_argv():
    captured = {}
    async def fake_save(reg): captured.update(reg)
    with patch.object(se, "_save_registration", AsyncMock(side_effect=fake_save)):
        await se.register_rollback("act-1", _tool(), {"host": "h1"}, ttl_seconds=60)
    assert captured["rollback_argv"] == ["unisolate", "h1"]
    assert captured["action_id"] == "act-1"


@pytest.mark.asyncio
async def test_execute_rollback_pages_oncall_on_failure():
    reg = SimpleNamespace(action_id="act-2", tool_name="isolator",
                          rollback_argv=["unisolate", "h1"], status="registered")
    with patch.object(se, "_load_registration", AsyncMock(return_value=reg)), \
         patch.object(se, "_mark", AsyncMock()), \
         patch.object(se, "run_command", AsyncMock(return_value={"exit_code": 1, "stderr": "boom"})), \
         patch.object(se, "_page_oncall", AsyncMock()) as page:
        ok = await se.execute_rollback("act-2")
    assert ok is False
    page.assert_awaited()   # on-call paged on rollback failure
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_safety_envelope.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.services.safety_envelope`.

- [ ] **Step 3: Implement `app/services/safety_envelope.py`**

```python
"""Safety Envelope: pre-validation, rollback registry, revert + paging (B6)."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
import httpx
from app.services.tool_executor import build_argv, TOOL_RUNNER_URL, RUNNER_TOKEN

ENVELOPE_CATEGORIES = {"contain_soft", "contain_hard", "remediate"}


def requires_envelope(category: str | None) -> bool:
    return (category or "").lower() in ENVELOPE_CATEGORIES


def has_rollback(tool) -> bool:
    return bool(getattr(tool, "rollback_command_template", None))


def _schema(tool) -> dict:
    try:
        return json.loads(tool.input_schema_json) if tool.input_schema_json else {}
    except json.JSONDecodeError:
        return {}


async def run_command(template: str, tool, args: dict, timeout: int = 60) -> dict:
    """Run a command template (validation/verification/rollback) in the tool-runner."""
    argv = build_argv(template, _schema(tool), args)
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        r = await client.post(f"{TOOL_RUNNER_URL}/run",
                              json={"argv": argv, "timeout": timeout},
                              headers={"X-Runner-Token": RUNNER_TOKEN})
    return r.json() if r.status_code == 200 else {"exit_code": -1, "stderr": r.text[:200]}


async def register_rollback(action_id: str, tool, args: dict, ttl_seconds: int = 3600) -> None:
    argv = build_argv(tool.rollback_command_template, _schema(tool), args)
    await _save_registration({
        "action_id": action_id,
        "tool_id": getattr(tool, "id", None),
        "tool_name": getattr(tool, "name", None),
        "rollback_argv": argv,
        "status": "registered",
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(seconds=ttl_seconds),
    })


async def execute_rollback(action_id: str) -> bool:
    reg = await _load_registration(action_id)
    if reg is None or reg.status != "registered":
        return False
    # rollback_argv is already built; run it directly.
    async with httpx.AsyncClient(timeout=70) as client:
        try:
            r = await client.post(f"{TOOL_RUNNER_URL}/run",
                                  json={"argv": reg.rollback_argv, "timeout": 60},
                                  headers={"X-Runner-Token": RUNNER_TOKEN})
            result = r.json() if r.status_code == 200 else {"exit_code": -1, "stderr": r.text[:200]}
        except Exception as e:
            result = {"exit_code": -1, "stderr": str(e)}
    if result.get("exit_code") == 0:
        await _mark(action_id, "reverted", None)
        return True
    await _mark(action_id, "failed", str(result.get("stderr"))[:500])
    await _page_oncall(action_id, reg.tool_name, result.get("stderr"))
    return False


# --- persistence + paging (kept thin so the logic above is unit-testable) ---
async def _save_registration(reg: dict) -> None:
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    async with get_db_context() as s:
        s.add(RollbackRegistration(**reg))
        await s.commit()


async def _load_registration(action_id: str):
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    from sqlalchemy import select
    async with get_db_context() as s:
        return (await s.execute(select(RollbackRegistration).where(
            RollbackRegistration.action_id == action_id))).scalar_one_or_none()


async def _mark(action_id: str, status: str, detail: str | None) -> None:
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    from sqlalchemy import select
    async with get_db_context() as s:
        reg = (await s.execute(select(RollbackRegistration).where(
            RollbackRegistration.action_id == action_id))).scalar_one_or_none()
        if reg:
            reg.status = status
            reg.detail = detail
            if status == "reverted":
                reg.reverted_at = datetime.utcnow()
            await s.commit()


async def _page_oncall(action_id: str, tool_name: str | None, stderr) -> None:
    try:
        from app.services import webhook_service
        await webhook_service.emit("rollback.failed",
                                   {"action_id": action_id, "tool": tool_name, "error": str(stderr)[:300]})
    except Exception:
        import logging
        logging.getLogger("safety_envelope").error(
            "ROLLBACK FAILED action=%s tool=%s err=%s", action_id, tool_name, str(stderr)[:300])
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_safety_envelope.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/safety_envelope.py tests/test_safety_envelope.py
git commit -m "feat(envelope): safety_envelope service (register/execute/page)"
```

### Task 4: Gatekeeper denies envelope action with no rollback

**Files:**
- Modify: `app/services/gatekeeper.py`
- Test: `tests/test_gatekeeper.py` (append)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_envelope_action_without_rollback_denied():
    r = gatekeeper_check(
        {"action_category": "contain_hard", "risk_tier": "high", "has_rollback": False},
        ctx(), confidence=0.99)
    assert r.decision is Decision.DENY and "rollback" in r.reason.lower()

def test_envelope_action_with_rollback_needs_approval():
    r = gatekeeper_check(
        {"action_category": "contain_hard", "risk_tier": "high", "has_rollback": True},
        ctx(), confidence=0.99)
    assert r.decision is Decision.NEEDS_APPROVAL
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_gatekeeper.py -k envelope -v
```
Expected: FAIL (currently NEEDS_APPROVAL for both).

- [ ] **Step 3: Add the rule to `gatekeeper_check`** — insert **before** the "Approval-by-default categories" rule (step 5 in the existing function):

```python
    # 4b. Safety envelope: contain/remediate MUST carry a rollback (NDB Std §Safety Envelope).
    ENVELOPE = {"contain_soft", "contain_hard", "remediate"}
    if cat in ENVELOPE and not tool_meta.get("has_rollback", False):
        return R(Decision.DENY, f"category '{cat}' requires a registered rollback procedure")
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_gatekeeper.py -v
```
Expected: all PASS (existing tools default `has_rollback` absent → treated False; existing envelope tests that expected NEEDS_APPROVAL must now pass `has_rollback=True` — update those two existing cases to include `"has_rollback": True` in their `tool_meta`).

- [ ] **Step 5: Update the two prior envelope tests** to include `"has_rollback": True` so they still assert NEEDS_APPROVAL, then re-run and commit.

```bash
.venv/bin/python -m pytest tests/test_gatekeeper.py -v
git add app/services/gatekeeper.py tests/test_gatekeeper.py
git commit -m "feat(envelope): gatekeeper denies contain/remediate without rollback"
```

### Task 5: Wire pre-validation + rollback registration into `execute_tool()`

**Files:**
- Modify: `app/services/tool_executor.py`
- Test: `tests/test_tool_executor.py` (append)

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_execute_tool_registers_rollback_on_envelope_success():
    from app.services import tool_executor as te
    from unittest.mock import AsyncMock, patch
    fake_resp = SimpleNamespace(status_code=200, json=lambda: {
        "stdout": "done", "stderr": "", "exit_code": 0, "duration_ms": 5, "timed_out": False})
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(return_value=fake_resp)
    tool = _tool(action_category="contain_soft", rollback_command_template="undo {msg}")
    with patch.object(te.httpx, "AsyncClient", return_value=client), \
         patch("app.services.safety_envelope.register_rollback", AsyncMock()) as reg:
        res = await te.execute_tool(tool, {"msg": "x"}, user_id=1, approved=True)
    assert res["status"] == "completed"
    reg.assert_awaited()                   # rollback registered after success
    assert "action_id" in res
```

Extend the `_tool` helper's `base` dict (top of file) to include the new attributes so it's a valid envelope tool:
```python
                action_category=None, risk_tier=None,
                rollback_command_template=None, validation_command_template=None,
                verification_command_template=None,
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_tool_executor.py -k rollback -v
```
Expected: FAIL — `register_rollback` not awaited / no `action_id` in result.

- [ ] **Step 3: Implement.** In `execute_tool()`:

(a) Add `has_rollback` to the gatekeeper's `tool_meta` (in the gatekeeper block from the prior plan):
```python
        tool_meta = {"action_category": getattr(tool, "action_category", None),
                     "risk_tier": getattr(tool, "risk_tier", None),
                     "has_rollback": bool(getattr(tool, "rollback_command_template", None))}
```

(b) Just **before** the tool-runner `httpx` call, run pre-validation for envelope tools:
```python
    from app.services.safety_envelope import requires_envelope
    _envelope = requires_envelope(getattr(tool, "action_category", None))
    if _envelope and getattr(tool, "validation_command_template", None):
        from app.services.safety_envelope import run_command
        pre = await run_command(tool.validation_command_template, tool, args)
        if pre.get("exit_code") != 0:
            return {"status": "error", "error": f"pre-action validation failed: {pre.get('stderr')}"}
```

(c) After a successful `{"status": "completed", ...}` result is built, register the rollback and attach `action_id`:
```python
    result = {  # existing completed dict
        "status": "completed", "stdout": _truncate(data.get("stdout", "")),
        "stderr": _truncate(data.get("stderr", "")), "exit_code": data.get("exit_code"),
        "duration_ms": data.get("duration_ms"), "timed_out": data.get("timed_out", False),
    }
    if _envelope and getattr(tool, "rollback_command_template", None):
        action_id = str(uuid.uuid4())
        from app.services.safety_envelope import register_rollback
        await register_rollback(action_id, tool, args, ttl_seconds=3600)
        result["action_id"] = action_id
    return result
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_tool_executor.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_tool_executor.py
git commit -m "feat(envelope): pre-validate + register rollback on envelope actions"
```

### Task 6: Rollback API + register router

**Files:**
- Create: `app/routers/governance_rollback.py`
- Modify: `app/main.py`

- [ ] **Step 1: Router** (admin-only; mirror sibling auth)

```python
# app/routers/governance_rollback.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.rbac import Permission, require_permission
from app.models.rollback import RollbackRegistration
from app.services.safety_envelope import execute_rollback

router = APIRouter()


@router.get("/governance/rollback")
async def list_rollbacks(db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.SETTINGS_READ))):
    rows = (await db.execute(select(RollbackRegistration).where(
        RollbackRegistration.status == "registered"))).scalars().all()
    return [{"action_id": r.action_id, "tool": r.tool_name, "expires_at": r.expires_at} for r in rows]


@router.post("/governance/rollback/{action_id}")
async def trigger_rollback(action_id: str,
                           _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    ok = await execute_rollback(action_id)
    if not ok:
        raise HTTPException(409, "rollback failed or not available (see audit/paging)")
    return {"action_id": action_id, "status": "reverted"}
```

- [ ] **Step 2: Register in `app/main.py`**

```python
from app.routers import governance_rollback as governance_rollback_router
app.include_router(governance_rollback_router.router, prefix="/api/v1", tags=["Safety Envelope"])
```

- [ ] **Step 3: Smoke-check + full suite + commit**

```bash
.venv/bin/python -c "import app.main; print('ok')"
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
git add app/routers/governance_rollback.py app/main.py
git commit -m "feat(envelope): rollback list + trigger API"
```

---

## Self-Review notes (coverage vs the Standard)

- **B6 pre-action validation** → Task 5(b): `validation_command_template` runs before the action; non-zero aborts.
- **B6 rollback procedure registered** → Tasks 2–3, 5(c): durable DB registry with TTL; argv computed from `rollback_command_template`.
- **B6 "if rollback fails, page on-call"** → Task 3 `_page_oncall` via `webhook_service.emit` (+ logger fallback).
- **Enforcement that envelope actions MUST have rollback** → Task 4: gatekeeper denies otherwise (stronger than the Standard, which only states the requirement).
- **Post-action verification** → `verification_command_template` column + `run_command` helper are in place; **auto-revert-on-verification-failure is left as a small follow-up wiring** in `execute_tool` (run verification after success; if non-zero → `execute_rollback` + page). Flagged here rather than silently claimed done.
- **Known limitations:** covers the executable **Tool pool** only — MCP-server-mediated tools need a parallel rollback mechanism (follow-up). Expired registrations are not swept by a background job yet (a periodic `status="expired"` sweeper is a minor add). Rollback argv is computed at registration from the original args — adequate for revert-by-inverse-command tools; tools needing captured runtime state (e.g. a dynamically-assigned id) must include it in their args.
- **Still open for later plans (unchanged):** `master.py` second-exec-path governance; POC evidence package + governance metrics; audit WORM export.
