# Black-Box Agent Wrapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Govern third-party / remote ("black box") agents per the Standard's *"Third-party black box agents must be wrapped."* Today the OpenClaw gateway hands an agent the raw tool `command_template` via `/gateway/manifest` and trusts it to run tools itself, reporting only a final result — its individual actions never pass the gatekeeper. This plan forces a **governed broker callback**: a wrapped agent is given tool *names + schemas only* (no executable command) and must call `POST /gateway/execute-tool`, which runs the action through the same governed `execute_tool()` chokepoint (gatekeeper + kill switch + audit + rollback). Un-wrapped external agents are capped to non-state-changing actions.

**Architecture:** A `governed` flag on `agent_configs`. For governed external agents the manifest **withholds `command_template`** (so the agent literally cannot execute locally) and the new broker endpoint executes on its behalf through `execute_tool()`. A new GovernanceContext flag `external_unwrapped` makes the gatekeeper **deny** any state-changing category for an external agent that isn't wrapped — so a true black box that refuses to broker can only ever do `observe`/`annotate`/`notify`. Core logic lives in a testable `agent_wrapper` service; the gateway endpoint is a thin wrapper.

**Tech Stack:** FastAPI, SQLAlchemy async, the gatekeeper/kill-switch/audit/execute_tool stack from the earlier plans, pytest. One small migration.

---

## Dependencies & decisions

- **Depends on:** the gatekeeper + `execute_tool()` governance wiring (controls plan), `load_governance()` (governance-config plan). Migration chains on the current head; numbered `031` assuming the WORM plan's `030` landed — set `down_revision` to the actual head at implementation time.
- **Trust model (be honest about it):** we cannot force a third-party binary to behave. The enforcement levers we *do* control:
  1. **Withhold the executable** — a governed agent's manifest carries no `command_template`, so it has nothing to run directly; it must broker.
  2. **Cap the ungoverned** — the gatekeeper denies state-changing categories to any external agent not marked `governed`, so refusing to broker = limited to read-only/notify.
  3. **Audit + detect** — every broker call is audited; reported results referencing un-brokered actions can be flagged (best-effort, follow-up).
- **Broker identity:** the agent authenticates with its existing `X-Api-Key`; the acting `user_id` is resolved from the originating `GatewayMessage.sender_user_id` (via `execution_id`), falling back to `0` (system).
- **Scope:** OpenClaw gateway agents (we own the protocol). Plain hermes/custom HTTP-push agents that don't speak the gateway are, by definition, capped to read-only by lever #2 until they adopt the broker — documented, not silently assumed governed.

## File Structure

| File | Responsibility |
|------|----------------|
| `app/models/agent.py` (modify) | `governed` boolean on `AgentConfig` |
| `alembic/versions/031_agent_governed_flag.py` (create) | Migrate the flag |
| `app/services/gatekeeper.py` (modify) | `external_unwrapped` field + deny-rule |
| `app/services/agent_wrapper.py` (create) | `governance_for_external()`, `broker_execute()` |
| `app/routers/gateway.py` (modify) | `POST /gateway/execute-tool`; manifest withholds `command_template` for governed agents |
| `tests/test_gatekeeper.py` (append) | external-unwrapped deny rule |
| `tests/test_agent_wrapper.py` (create) | broker routes through execute_tool; halted; context |
| `tests/test_gateway_manifest.py` (append) | governed manifest omits command_template |

---

### Task 1: `governed` flag on `AgentConfig`

**Files:**
- Modify: `app/models/agent.py`
- Create: `alembic/versions/031_agent_governed_flag.py`

- [ ] **Step 1: Add the column** (near the other governance columns):

```python
    governed = Column(Boolean, nullable=False, server_default="false", default=False)  # wrapped: must broker tool calls
```

- [ ] **Step 2: Migration `031_agent_governed_flag.py`**

```python
"""agent_configs: governed (wrapped) flag

Revision ID: 031_agent_governed_flag
Revises: 030_audit_worm_exports
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "031_agent_governed_flag"
down_revision = "030_audit_worm_exports"
branch_labels = None
depends_on = None


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_configs")}


def upgrade() -> None:
    if "governed" not in _existing():
        op.add_column("agent_configs",
                      sa.Column("governed", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    if "governed" in _existing():
        op.drop_column("agent_configs", "governed")
```

- [ ] **Step 3: Migrate + commit**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
git add app/models/agent.py alembic/versions/031_agent_governed_flag.py
git commit -m "feat(wrap): governed (wrapped) flag on agent_configs"
```

### Task 2: Gatekeeper deny-rule for un-wrapped external agents

**Files:**
- Modify: `app/services/gatekeeper.py`
- Test: `tests/test_gatekeeper.py` (append)

- [ ] **Step 1: Write the failing tests** (append; reuses the file's `ctx()` helper)

```python
def test_external_unwrapped_blocked_from_state_change():
    r = gatekeeper_check({"action_category": "contain_soft", "risk_tier": "low", "has_rollback": True},
                         ctx(external_unwrapped=True), confidence=0.99)
    assert r.decision is Decision.DENY and "wrapped" in r.reason.lower()

def test_external_unwrapped_allowed_readonly():
    r = gatekeeper_check({"action_category": "observe", "risk_tier": "low"},
                         ctx(external_unwrapped=True), confidence=0.99)
    assert r.decision is Decision.ALLOW
```

- [ ] **Step 2: Add `external_unwrapped` to `GovernanceContext`** (default keeps every existing call working):

```python
    external_unwrapped: bool = False
```

Update the `ctx()` test helper's `base` dict (in `tests/test_gatekeeper.py`) to include `external_unwrapped=False`.

- [ ] **Step 3: Add the rule to `gatekeeper_check`** — insert right **after** the kill-switch check (rule 1), before the POC-forbidden check:

```python
    # 1b. Un-wrapped external/black-box agents: read-only/notify only (NDB Std §Scope).
    SAFE_FOR_UNWRAPPED = {"observe", "annotate", "notify"}
    if gov.external_unwrapped and cat not in SAFE_FOR_UNWRAPPED:
        return R(Decision.DENY, f"external agent is not wrapped; '{cat}' requires a governed (brokered) agent")
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_gatekeeper.py -v
```
Expected: all PASS (existing tests default `external_unwrapped=False` → unaffected).

- [ ] **Step 5: Commit**

```bash
git add app/services/gatekeeper.py tests/test_gatekeeper.py
git commit -m "feat(wrap): gatekeeper caps un-wrapped external agents to read-only"
```

### Task 3: Agent-wrapper broker service

**Files:**
- Create: `app/services/agent_wrapper.py`
- Test: `tests/test_agent_wrapper.py`

- [ ] **Step 1: Write the failing tests** (DB-free; mock `execute_tool`)

```python
# tests/test_agent_wrapper.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services import agent_wrapper as aw
from app.services.gatekeeper import GovernanceContext


def _agent(**kw):
    base = dict(id=3, agent_name="remote-ir", kind="external", governed=True,
                autonomy_tier="L2", allowed_categories=["observe", "contain_hard"],
                escalate_to_human_below=0.60, is_poc=True)
    base.update(kw)
    return SimpleNamespace(**base)


def test_governance_for_external_unwrapped_when_not_governed():
    ctx = aw.governance_for_external(_agent(governed=False))
    assert isinstance(ctx, GovernanceContext) and ctx.external_unwrapped is True


def test_governance_for_external_wrapped_when_governed():
    ctx = aw.governance_for_external(_agent(governed=True))
    assert ctx.external_unwrapped is False


@pytest.mark.asyncio
async def test_broker_execute_routes_through_execute_tool():
    tool = SimpleNamespace(id=9, name="isolate", action_category="contain_hard",
                           rollback_command_template="unisolate {host}")
    with patch.object(aw, "execute_tool", AsyncMock(return_value={"status": "completed"})) as et:
        res = await aw.broker_execute(_agent(), tool, user_id=7,
                                      args={"host": "h1"}, confidence=0.9)
    assert res["status"] == "completed"
    _, kwargs = et.call_args
    assert isinstance(kwargs["governance"], GovernanceContext)   # governed context passed
    assert kwargs["confidence"] == 0.9
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_agent_wrapper.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.services.agent_wrapper`.

- [ ] **Step 3: Implement `app/services/agent_wrapper.py`**

```python
"""Wrap external/black-box agents: route their tool calls through the governed
execute_tool() chokepoint (NDB Std §Scope — black-box agents must be wrapped)."""
from __future__ import annotations
from app.services.gatekeeper import GovernanceContext
from app.services.governance_config import load_governance
from app.services.tool_executor import execute_tool

DEFAULT_ALLOWED = ["observe", "annotate", "notify", "contain_soft"]


def governance_for_external(agent) -> GovernanceContext:
    """Like load_governance, but marks external+un-governed agents as un-wrapped
    so the gatekeeper caps them to read-only/notify."""
    ctx = load_governance(agent)
    kind = getattr(agent, "kind", "external")
    ctx.external_unwrapped = (kind == "external") and not bool(getattr(agent, "governed", False))
    return ctx


async def broker_execute(agent, tool, user_id: int, args: dict, confidence: float | None) -> dict:
    """Execute one tool on behalf of a wrapped agent through the governed path."""
    governance = governance_for_external(agent)
    return await execute_tool(tool, args, user_id=user_id,
                              governance=governance, confidence=confidence)
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_agent_wrapper.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/agent_wrapper.py tests/test_agent_wrapper.py
git commit -m "feat(wrap): agent_wrapper broker — route external agent tools through execute_tool"
```

### Task 4: Gateway broker endpoint + manifest withholding

**Files:**
- Modify: `app/routers/gateway.py`

- [ ] **Step 1: Add the broker request schema** (near the other schemas)

```python
class ExecuteToolRequest(BaseModel):
    execution_id: Optional[str] = None
    tool_id: int
    args: dict = Field(default_factory=dict)
    confidence: Optional[float] = None
```

- [ ] **Step 2: Add the broker endpoint** (after `report`)

```python
@router.post("/gateway/execute-tool")
async def gateway_execute_tool(body: ExecuteToolRequest,
                               x_api_key: str = Header(..., alias="X-Api-Key")):
    """Governed tool execution for wrapped agents. The agent calls this instead
    of running the tool itself; the action passes the full gatekeeper."""
    agent = await _auth_agent(x_api_key)
    allowed_ids = set(agent.associated_tools or [])
    if body.tool_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="tool not assigned to this agent")

    async with AsyncSessionLocal() as session:
        tool = (await session.execute(
            select(Tool).where(Tool.id == body.tool_id, Tool.is_active.is_(True)))).scalar_one_or_none()
        if tool is None:
            raise HTTPException(status_code=404, detail="tool not found")
        # Resolve the originating human for approval routing / audit.
        user_id = 0
        if body.execution_id:
            gm = (await session.execute(
                select(GatewayMessage).where(GatewayMessage.execution_id == body.execution_id)
            )).scalar_one_or_none()
            if gm and gm.sender_user_id:
                user_id = gm.sender_user_id

    from app.services.agent_wrapper import broker_execute
    return await broker_execute(agent, tool, user_id=user_id, args=body.args, confidence=body.confidence)
```

Add the imports `GatewayMessage` and `Tool` to the file's import block if not already present.

- [ ] **Step 3: Withhold `command_template` for governed agents in `/gateway/manifest`** — change the `ManifestTool(...)` construction:

```python
            tools.append(ManifestTool(
                id=t.id, name=t.name, description=t.description,
                command_template=None if agent.governed else t.command_template,
                input_schema=schema,
            ))
```

And surface the mode on the response so the agent knows to broker — add `governed` to `ManifestResponse` and set it:

```python
    return ManifestResponse(
        agent_id=agent.id, agent_name=agent.agent_name, governed=bool(agent.governed),
        skills=skills, tools=tools, mcp_tools=mcp_tools,
    )
```

Add `governed: bool = False` to the `ManifestResponse` Pydantic model.

- [ ] **Step 4: Write the manifest test** (append to `tests/test_gateway_manifest.py`, matching that file's existing setup/fixtures)

```python
@pytest.mark.asyncio
async def test_manifest_withholds_command_template_for_governed_agent(...):
    # Arrange a governed agent (governed=True) assigned one Tool with a command_template,
    # following this file's existing arrange/auth pattern, then:
    resp = await call_manifest(api_key=governed_agent_key)   # use the file's helper
    assert resp["governed"] is True
    assert resp["tools"][0]["command_template"] is None
```

> Mirror the existing `test_gateway_manifest.py` fixtures (DB seeding + `X-Api-Key`); only the `governed=True` arrange and the two assertions are new.

- [ ] **Step 5: Run the gateway tests + smoke-check**

```bash
.venv/bin/python -c "import app.routers.gateway; print('ok')"
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_gateway_manifest.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routers/gateway.py tests/test_gateway_manifest.py
git commit -m "feat(wrap): governed tool broker endpoint + manifest withholds command_template"
```

**Plan gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

## Self-Review notes (coverage vs the Standard)

- **"Black box agents must be wrapped"** → a `governed` agent receives no executable `command_template` and must call `POST /gateway/execute-tool`, which runs through `execute_tool()` — so its actions now hit the gatekeeper, kill switch, audit, and rollback registration exactly like an internal agent.
- **Refusal is contained, not just trusted** → an external agent left un-wrapped (`governed=False`) is denied every state-changing category by the gatekeeper (`external_unwrapped` rule), so a non-cooperating black box is limited to `observe`/`annotate`/`notify`. This is the honest enforcement boundary: we cannot make a third-party binary cooperate, but we can ensure it cannot do damage if it doesn't.
- **Audit/approval identity** → broker calls resolve the originating `sender_user_id` for approval routing (A3) and audit attribution.
- **Known limitations / follow-ups:** (1) **Detection of out-of-band actions** — a wrapped agent could still *act* outside the broker and only report results; cross-checking reported results against brokered actions per `execution_id` (and flagging mismatches) is a best-effort follow-up. (2) **MCP tools via broker** — this routes Tool-pool tools; brokering MCP-server tools needs the parallel MCP execution path. (3) **Network egress** — truly sandboxing a black box also wants tool-runner/agent egress allowlisting (separate "egress policy" plan). (4) `hermes`/`custom` push agents must adopt the broker to do state-changing work; until then lever #2 caps them.
- **With this plan, the last open NDB item is closed.** Remaining ideas are beyond-Standard hardening (signed audit, egress policy, governance dashboard, red-team CI gate).
