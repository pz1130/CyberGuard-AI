# Governance Config & Risk-Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every agent a first-class, declarative governance configuration (B1) — autonomy tier, allowed action categories, confidence thresholds, PII policy, kill-switch flag — surfaced in the API/WebUI and exportable as the Standard's `agent_governance.yaml` (Appendix B); and route approvals by risk tier to the correct approver role (completes A1 declaration + A3 routing).

**Architecture:** Add governance columns to the existing `agent_configs` table and a `governance_config` service that (a) builds the `GovernanceContext` consumed by the Phase-2 gatekeeper — **superseding** the temporary `metadata_json` default-reading — and (b) exports the Standard's YAML. Add a `required_approver_role` to approval requests, derived from the action's `risk_tier`, and enforce it at decision time.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, Alembic, PyYAML 6.0.3, pytest/pytest-asyncio. Naive-UTC timestamps. RBAC roles: `admin/operator/analyst/viewer/auditor` (`app/core/rbac.py`).

---

## Dependency & decisions

- **Depends on the prior plan** `2026-06-09-agent-governance-controls.md` (Phases 1–3): this plan reuses `app/services/gatekeeper.py::GovernanceContext` and the `execute_tool()` gatekeeper wiring, and its migrations chain on top (`025_kill_switch` → `026` → `027`). Land that plan first.
- **Standard mapping for A1:** POCs default `L2`; **`L4` is forbidden** (reject on save); **`L3` requires a recorded Chief-of-IT authorization reference** (`l3_authorization_ref`).
- **Standard mapping for A3** (risk tier → approver). RBAC has no "Security Director"/"SOC Manager" roles, so store the Standard's **label** for display and enforce a **minimum RBAC role**:

  | risk_tier | approver label (Standard) | enforced min role | approval needed? |
  |-----------|---------------------------|-------------------|------------------|
  | critical  | Security Director + Legal | `admin`           | yes |
  | high      | SOC Manager               | `admin`           | yes |
  | medium    | Senior SOC Analyst        | `analyst`         | yes |
  | low       | Agent operator (logged)   | —                 | no (logged only) |

## File Structure

| File | Responsibility |
|------|----------------|
| `app/models/agent.py` (modify) | Governance columns on `AgentConfig` |
| `alembic/versions/026_agent_governance.py` (create) | Migrate agent governance columns |
| `app/models/approval.py` (modify) | `required_approver_role` column |
| `alembic/versions/027_approval_approver_role.py` (create) | Migrate the column |
| `app/services/governance_config.py` (create) | `load_governance()`, `export_yaml()`, `validate_autonomy()`, `approver_for_risk()` |
| `app/routers/governance_config.py` (create) | GET/PUT `/agents/{id}/governance`, GET `…/governance.yaml` |
| `app/main.py` (modify) | Register the router |
| `app/services/approval_service.py` (modify) | Store + enforce `required_approver_role` |
| `app/services/tool_executor.py` (modify) | `_create_approval` sets risk + approver role |
| `app/services/internal_agent.py` (modify) | Use `load_governance()` (supersede metadata_json block) |
| `tests/test_governance_config.py` (create) | Service + export + validation tests |
| `tests/test_approval_routing.py` (create) | Risk→role routing + enforcement tests |

---

### Task 1: Governance columns on `AgentConfig`

**Files:**
- Modify: `app/models/agent.py`
- Create: `alembic/versions/026_agent_governance.py`

- [ ] **Step 1: Add columns to `AgentConfig`** (after `metadata_json`, before `kind`):

```python
    # --- Declarative governance (NDB Std §Mandatory Governance Taxonomy / B1) ---
    autonomy_tier = Column(String(8), nullable=False, server_default="L2", default="L2")  # L0..L4 (L4 forbidden)
    l3_authorization_ref = Column(String(255), nullable=True)   # Chief-of-IT approval ref when tier == L3
    allowed_categories = Column(JSON, nullable=True)            # list[str]; None → service default
    auto_execute_min_confidence = Column(Float, nullable=False, server_default="0.85", default=0.85)
    escalate_to_human_below = Column(Float, nullable=False, server_default="0.60", default=0.60)
    pii_handling_policy = Column(String(20), nullable=False, server_default="redact", default="redact")  # redact|pseudonymize|block
    kill_switch_enabled = Column(Boolean, nullable=False, server_default="true", default=True)
    is_poc = Column(Boolean, nullable=False, server_default="true", default=True)
    requires_approval_rules = Column(JSON, nullable=True)       # list[{action, condition}]
```

Add `Float` to the imports line:
```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Float
```

- [ ] **Step 2: Migration `026_agent_governance.py`** (idempotent; head is `025_kill_switch`)

```python
"""agent_configs: declarative governance columns

Revision ID: 026_agent_governance
Revises: 025_kill_switch
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "026_agent_governance"
down_revision = "025_kill_switch"
branch_labels = None
depends_on = None

_COLUMNS = {
    "autonomy_tier": sa.Column("autonomy_tier", sa.String(8), nullable=False, server_default="L2"),
    "l3_authorization_ref": sa.Column("l3_authorization_ref", sa.String(255), nullable=True),
    "allowed_categories": sa.Column("allowed_categories", sa.JSON(), nullable=True),
    "auto_execute_min_confidence": sa.Column("auto_execute_min_confidence", sa.Float(), nullable=False, server_default="0.85"),
    "escalate_to_human_below": sa.Column("escalate_to_human_below", sa.Float(), nullable=False, server_default="0.60"),
    "pii_handling_policy": sa.Column("pii_handling_policy", sa.String(20), nullable=False, server_default="redact"),
    "kill_switch_enabled": sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False, server_default="true"),
    "is_poc": sa.Column("is_poc", sa.Boolean(), nullable=False, server_default="true"),
    "requires_approval_rules": sa.Column("requires_approval_rules", sa.JSON(), nullable=True),
}


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_configs")}


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("agent_configs", column)


def downgrade() -> None:
    existing = _existing()
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("agent_configs", name)
```

- [ ] **Step 3: Migrate + commit**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
git add app/models/agent.py alembic/versions/026_agent_governance.py
git commit -m "feat(governance): declarative governance columns on agent_configs"
```

### Task 2: `governance_config` service

**Files:**
- Create: `app/services/governance_config.py`
- Test: `tests/test_governance_config.py`

- [ ] **Step 1: Write the failing tests** (DB-free; uses `SimpleNamespace` like `test_tool_executor.py`)

```python
# tests/test_governance_config.py
import pytest
from types import SimpleNamespace
from app.services import governance_config as gc
from app.services.gatekeeper import GovernanceContext

DEFAULT_CATS = ["observe", "annotate", "notify", "contain_soft"]


def _agent(**kw):
    base = dict(agent_name="threat_intel", autonomy_tier="L2", allowed_categories=None,
                auto_execute_min_confidence=0.85, escalate_to_human_below=0.60,
                pii_handling_policy="redact", kill_switch_enabled=True, is_poc=True,
                requires_approval_rules=None, l3_authorization_ref=None,
                associated_tools=[], audit_log_path=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_load_governance_applies_defaults():
    ctx = gc.load_governance(_agent())
    assert isinstance(ctx, GovernanceContext)
    assert ctx.autonomy_tier == "L2"
    assert ctx.allowed_categories == DEFAULT_CATS    # None → default list
    assert ctx.escalate_below == 0.60
    assert ctx.is_poc is True


def test_load_governance_respects_explicit_categories():
    ctx = gc.load_governance(_agent(allowed_categories=["observe", "contain_hard"]))
    assert ctx.allowed_categories == ["observe", "contain_hard"]


def test_validate_autonomy_rejects_l4():
    with pytest.raises(ValueError, match="L4"):
        gc.validate_autonomy("L4", l3_ref=None)


def test_validate_autonomy_l3_requires_ref():
    with pytest.raises(ValueError, match="Chief of IT"):
        gc.validate_autonomy("L3", l3_ref=None)
    gc.validate_autonomy("L3", l3_ref="CIO-2026-014")   # ok with ref


def test_export_yaml_matches_appendix_b_shape():
    y = gc.export_yaml(_agent(agent_name="ir_agent", autonomy_tier="L2"))
    import yaml
    d = yaml.safe_load(y)
    assert d["agent_name"] == "ir_agent"
    assert d["autonomy_tier"] == "L2"
    for key in ("allowed_actions", "auto_execute_min_confidence",
                "escalate_to_human_below", "pii_handling_policy",
                "kill_switch_enabled", "audit_log_path"):
        assert key in d


def test_approver_for_risk_mapping():
    assert gc.approver_for_risk("critical")["min_role"] == "admin"
    assert gc.approver_for_risk("medium")["min_role"] == "analyst"
    assert gc.approver_for_risk("low")["needs_approval"] is False
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_governance_config.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.services.governance_config`.

- [ ] **Step 3: Implement `app/services/governance_config.py`**

```python
"""Declarative agent governance (NDB Std §B1 / A1 / A3).

Single source of truth for an agent's governance, replacing the temporary
metadata_json default-reading. Builds the GovernanceContext the gatekeeper
consumes, exports the Standard's agent_governance.yaml, and maps risk tier to
the required approver.
"""
from __future__ import annotations
import yaml
from app.services.gatekeeper import GovernanceContext

DEFAULT_ALLOWED = ["observe", "annotate", "notify", "contain_soft"]

# A3 — risk tier → approver routing (Standard §Risk Tier)
_RISK_APPROVER = {
    "critical": {"label": "Security Director + Legal", "min_role": "admin",   "needs_approval": True},
    "high":     {"label": "SOC Manager",               "min_role": "admin",   "needs_approval": True},
    "medium":   {"label": "Senior SOC Analyst",        "min_role": "analyst", "needs_approval": True},
    "low":      {"label": "Agent operator (logged)",   "min_role": None,      "needs_approval": False},
}
# RBAC role privilege ordering for "meets min role" checks.
_ROLE_RANK = {"viewer": 0, "auditor": 0, "analyst": 1, "operator": 2, "admin": 3}


def _get(obj, name, default=None):
    """Read from an ORM row or a plain dict uniformly."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def validate_autonomy(tier: str, l3_ref: str | None) -> None:
    t = (tier or "L2").upper()
    if t == "L4":
        raise ValueError("Autonomy tier L4 (fully autonomous) is forbidden by the Standard.")
    if t == "L3" and not l3_ref:
        raise ValueError("Autonomy tier L3 requires a prior Chief of IT authorization reference.")


def load_governance(agent) -> GovernanceContext:
    cats = _get(agent, "allowed_categories")
    return GovernanceContext(
        autonomy_tier=_get(agent, "autonomy_tier", "L2") or "L2",
        allowed_categories=cats if cats else list(DEFAULT_ALLOWED),
        escalate_below=float(_get(agent, "escalate_to_human_below", 0.60) or 0.60),
        is_poc=bool(_get(agent, "is_poc", True)),
        halted=False,  # set by the kill-switch check at the chokepoint
    )


def approver_for_risk(risk_tier: str | None) -> dict:
    return _RISK_APPROVER.get((risk_tier or "low").lower(), _RISK_APPROVER["low"])


def role_meets(role: str | None, min_role: str | None) -> bool:
    if not min_role:
        return True
    return _ROLE_RANK.get((role or "viewer").lower(), 0) >= _ROLE_RANK[min_role]


def export_yaml(agent) -> str:
    cats = _get(agent, "allowed_categories") or DEFAULT_ALLOWED
    doc = {
        "agent_name": _get(agent, "agent_name"),
        "autonomy_tier": _get(agent, "autonomy_tier", "L2"),
        "allowed_actions": list(cats),
        "requires_approval": _get(agent, "requires_approval_rules") or [],
        "auto_execute_min_confidence": float(_get(agent, "auto_execute_min_confidence", 0.85) or 0.85),
        "escalate_to_human_below": float(_get(agent, "escalate_to_human_below", 0.60) or 0.60),
        "pii_handling_policy": _get(agent, "pii_handling_policy", "redact"),
        "audit_log_path": _get(agent, "audit_log_path") or "db://audit_logs",
        "kill_switch_enabled": bool(_get(agent, "kill_switch_enabled", True)),
    }
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_governance_config.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/governance_config.py tests/test_governance_config.py
git commit -m "feat(governance): governance_config service (load/export/validate/route)"
```

### Task 3: Governance API router (read / update / YAML export)

**Files:**
- Create: `app/routers/governance_config.py`
- Modify: `app/main.py`

- [ ] **Step 1: Implement the router** (mirror `master_config.py` auth: `require_permission`)

```python
# app/routers/governance_config.py
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.rbac import Permission, require_permission
from app.models.agent import AgentConfig
from app.services import governance_config as gc

router = APIRouter()


class GovernanceBody(BaseModel):
    autonomy_tier: str = "L2"
    l3_authorization_ref: str | None = None
    allowed_categories: list[str] | None = None
    auto_execute_min_confidence: float = 0.85
    escalate_to_human_below: float = 0.60
    pii_handling_policy: str = "redact"
    kill_switch_enabled: bool = True
    is_poc: bool = True
    requires_approval_rules: list[dict] | None = None


async def _get_agent(db: AsyncSession, agent_id: int) -> AgentConfig:
    agent = (await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))).scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, "agent not found")
    return agent


@router.get("/agents/{agent_id}/governance")
async def get_governance(agent_id: int, db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.SETTINGS_READ))):
    a = await _get_agent(db, agent_id)
    return {k: getattr(a, k) for k in GovernanceBody.model_fields}


@router.put("/agents/{agent_id}/governance")
async def put_governance(agent_id: int, body: GovernanceBody,
                         db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    try:
        gc.validate_autonomy(body.autonomy_tier, body.l3_authorization_ref)
    except ValueError as e:
        raise HTTPException(400, str(e))
    a = await _get_agent(db, agent_id)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    await db.commit()
    return {"status": "updated", "agent_id": agent_id}


@router.get("/agents/{agent_id}/governance.yaml")
async def export_governance_yaml(agent_id: int, db: AsyncSession = Depends(get_db),
                                 _=Depends(require_permission(Permission.SETTINGS_READ))):
    a = await _get_agent(db, agent_id)
    return Response(content=gc.export_yaml(a), media_type="application/x-yaml")
```

> If `Permission.SETTINGS_READ/WRITE` names differ in `app/core/rbac.py`, use the exact members that `app/routers/master_config.py` imports.

- [ ] **Step 2: Register in `app/main.py`** (near the other `include_router` lines)

```python
from app.routers import governance_config as governance_config_router
app.include_router(governance_config_router.router, prefix="/api/v1", tags=["Agent Governance Config"])
```

- [ ] **Step 3: Smoke-check import + commit**

```bash
.venv/bin/python -c "import app.main; print('ok')"
git add app/routers/governance_config.py app/main.py
git commit -m "feat(governance): GET/PUT /agents/{id}/governance + YAML export endpoint"
```

### Task 4: Feed `load_governance()` into the agent loop (supersede metadata_json)

**Files:**
- Modify: `app/services/internal_agent.py`
- Modify: `app/services/agent_executor.py` (config-dict assembly — include the governance columns)

- [ ] **Step 1: Ensure the governance columns reach the runner's config dict.** Where `agent_executor.py` builds the config dict passed to the internal-agent runner, add the governance fields from the `AgentConfig` row (match the surrounding key-copying style):

```python
    "autonomy_tier": agent.autonomy_tier,
    "allowed_categories": agent.allowed_categories,
    "escalate_to_human_below": agent.escalate_to_human_below,
    "auto_execute_min_confidence": agent.auto_execute_min_confidence,
    "is_poc": agent.is_poc,
    "agent_name": agent.agent_name,
```

- [ ] **Step 2: Replace the Phase-2 metadata_json block** in `internal_agent.py` with the service call:

```python
from app.services.governance_config import load_governance

governance = load_governance(self.config)   # supersedes the metadata_json["governance"] default-reading
result = await execute_tool(tool, call_args, user_id=self.user_id,
                            governance=governance, confidence=None)
```

- [ ] **Step 3: Run the internal-agent + governance tests**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_internal_agent.py tests/test_governance_config.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/services/internal_agent.py app/services/agent_executor.py
git commit -m "feat(governance): agents load declarative GovernanceContext from config"
```

### Task 5: Risk-tier → approver routing (A3)

**Files:**
- Modify: `app/models/approval.py`, create `alembic/versions/027_approval_approver_role.py`
- Modify: `app/services/approval_service.py`, `app/services/tool_executor.py`
- Test: `tests/test_approval_routing.py`

- [ ] **Step 1: Add `required_approver_role` to the model** (in `ApprovalRequest`, after `risk_level`):

```python
    required_approver_role = Column(String(20), nullable=True)   # min RBAC role to decide (A3 routing)
    required_approver_label = Column(String(100), nullable=True) # Standard's approver label (display)
```

- [ ] **Step 2: Migration `027_approval_approver_role.py`**

```python
"""approval_requests: add required_approver_role + label (A3 routing)

Revision ID: 027_approval_approver_role
Revises: 026_agent_governance
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "027_approval_approver_role"
down_revision = "026_agent_governance"
branch_labels = None
depends_on = None

_COLUMNS = {
    "required_approver_role": sa.Column("required_approver_role", sa.String(20), nullable=True),
    "required_approver_label": sa.Column("required_approver_label", sa.String(100), nullable=True),
}


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("approval_requests")}


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("approval_requests", column)


def downgrade() -> None:
    existing = _existing()
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("approval_requests", name)
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_approval_routing.py
import pytest
import uuid
from app.services.approval_service import ApprovalService
from app.services.governance_config import approver_for_risk, role_meets


def test_routing_table():
    assert approver_for_risk("critical")["min_role"] == "admin"
    assert approver_for_risk("low")["needs_approval"] is False
    assert role_meets("analyst", "admin") is False
    assert role_meets("admin", "admin") is True
    assert role_meets("analyst", "analyst") is True


@pytest.mark.asyncio
async def test_create_request_stores_required_role():
    rid = str(uuid.uuid4())
    rec = await ApprovalService().create_request(
        request_id=rid, user_id=1, action_type="tool.execute",
        action_description="block_ip", risk_level="critical")
    assert rec.required_approver_role == "admin"
    assert "Legal" in (rec.required_approver_label or "")


@pytest.mark.asyncio
async def test_decide_rejects_insufficient_role():
    rid = str(uuid.uuid4())
    await ApprovalService().create_request(
        request_id=rid, user_id=1, action_type="tool.execute",
        action_description="block_ip", risk_level="critical")
    with pytest.raises(PermissionError):
        await ApprovalService.decide(rid, "approved", approver_id=2,
                                     comment="ok", approver_role="analyst")
```

- [ ] **Step 4: Run to verify failure**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_approval_routing.py -v
```
Expected: FAIL — `required_approver_role` is `None` / `decide()` has no `approver_role` arg.

- [ ] **Step 5: Implement** — in `app/services/approval_service.py`:

In `create_request`, after computing `expires_at`, derive routing and store it:
```python
        from app.services.governance_config import approver_for_risk
        routing = approver_for_risk(risk_level)
```
and add to the `ApprovalRequest(...)` constructor:
```python
                required_approver_role=routing["min_role"],
                required_approver_label=routing["label"],
```

In `decide`, add an optional `approver_role` kwarg and enforce it:
```python
    @staticmethod
    async def decide(request_id, decision, approver_id, comment=None, approver_role=None):
        from app.services.governance_config import role_meets
        ...
        # after loading `record`, before writing the decision:
        if decision == "approved" and not role_meets(approver_role, record.required_approver_role):
            raise PermissionError(
                f"role '{approver_role}' cannot approve a '{record.risk_level}' action "
                f"(requires '{record.required_approver_role}')")
```

> Keep `approver_role=None` defaulting to "no check" so existing callers (and the auto-approve path) are unaffected; the approval router passes the current user's role.

- [ ] **Step 6: Set risk tier when the gatekeeper raises an approval** — in `app/services/tool_executor.py::_create_approval`, pass the tool's risk through:

```python
async def _create_approval(tool, args, user_id):
    from app.services.approval_service import ApprovalService
    await ApprovalService().create_request(
        request_id=str(uuid.uuid4()), user_id=user_id, action_type="tool.execute",
        action_description=f"Execute tool {getattr(tool, 'name', '?')}",
        payload={"tool": getattr(tool, "name", None), "args": args},
        risk_level=getattr(tool, "risk_tier", None) or "high")
```

- [ ] **Step 7: Run to verify pass**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_approval_routing.py tests/test_approval_service.py -v
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/models/approval.py alembic/versions/027_approval_approver_role.py \
        app/services/approval_service.py app/services/tool_executor.py tests/test_approval_routing.py
git commit -m "feat(governance): risk-tier approver routing (A3) + enforcement in decide()"
```

### Task 6: WebUI — Governance tab on the agent editor

**Files:**
- Modify: `webui/src` (agent editor)

- [ ] **Step 1: Add a "Governance / 治理" tab/section** to the agent edit page that reads `GET /api/v1/agents/{id}/governance`, edits the fields (autonomy_tier as an `L0–L3` select — **omit L4**; categories multi-select; the two confidence sliders; PII policy select; kill-switch + POC toggles), saves via `PUT`, and offers a "Download YAML" button hitting `…/governance.yaml`. Follow the existing agent-editor + API-client conventions (mirror how the MCP/Backup pages call the API and how `master_config` is edited). Bilingual labels per the project's i18n pattern.

- [ ] **Step 2: Commit**

```bash
git add webui/src
git commit -m "feat(governance): agent-editor Governance tab + YAML download"
```

**Plan gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

## Self-Review notes (coverage vs the Standard)

- **B1 Governance Config** → Tasks 1–3 (columns, service, API, YAML export = Appendix B shape). Now a first-class, queryable, exportable declaration.
- **A1 Autonomy declaration** → Tasks 1–3: tier is declared per agent; `validate_autonomy` enforces **L4 forbidden** and **L3 needs Chief-of-IT ref**; the WebUI omits L4. Runtime enforcement of the ceiling already lands in the prior plan's gatekeeper.
- **A3 Risk routing** → Task 5: risk tier → approver label + min role, stored on the request and enforced in `decide()`; `low` is logged-only (no approval).
- **Supersession** → Task 4 replaces the prior plan's temporary `metadata_json` governance reading with `load_governance()` off the new columns.
- **Still open for later plans (unchanged):** A5 PII pre-LLM redaction; B6 Safety-Envelope rollback registry; the `master.py` second-exec-path governance wiring; the POC evidence package + governance metrics; audit WORM export. Each warrants its own plan.
