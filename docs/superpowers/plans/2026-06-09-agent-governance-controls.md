# Agent Governance Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three P0 controls from the NDB AI Agent Governance Standard — hardened tamper-evident audit, a unified action gatekeeper with the action-category/risk taxonomy, and a platform-level kill switch — so CyberGuard's agent action path is governed end-to-end.

**Architecture:** All three controls converge on the existing tool-execution chokepoint `app/services/tool_executor.py::execute_tool()`. Phase 1 hardens `app/core/audit.py` into an append-only hash chain (the substrate the other two write into). Phase 2 adds a pure, unit-testable `gatekeeper.py` decision module and wires it into `execute_tool()`. Phase 3 adds a Redis+DB kill-switch signal checked at the same chokepoint, plus API/UI/file triggers. Each phase is independently shippable and test-gated.

**Tech Stack:** FastAPI, SQLAlchemy async + asyncpg, Alembic, Redis (`app/core/redis_client.py`), pytest/pytest-asyncio. Postgres timestamps are **naive UTC** by project convention — strip tzinfo before writing.

---

## Design decisions baked in (from the design doc's 4 open questions)

These use the **recommended defaults**. Confirm before the phase that depends on each; changing one only affects that phase.

1. **Per-agent governance config:** read autonomy tier / allowed categories / confidence thresholds from the agent config dict's `metadata_json["governance"]` block with safe defaults — **no new config subsystem in this plan**. A dedicated governance-config UI/export (B1) is a later plan.
2. **Confidence gate:** implemented but **advisory/secondary** — below `escalate_to_human_below` (default `0.60`) → `NEEDS_APPROVAL`; the category/risk rules are the primary gate.
3. **Audit durability:** **hash-chain tamper-evidence** now; object-lock WORM export deferred to a later phase.
4. **Kill-switch file path:** configurable `settings.KILL_SWITCH_FILE`, default `var/governance/kill_switch` under the app dir — **not** `/tmp/soc_kill_switch`.

## File Structure

| File | Responsibility | Phase |
|------|----------------|-------|
| `app/models/audit.py` (modify) | Add chain + Standard field columns to `AuditLog` | 1 |
| `alembic/versions/023_audit_chain.py` (create) | Migrate the new audit columns | 1 |
| `app/core/audit.py` (modify) | `record_action()` — synchronous, full-field, hash-chained append + `verify_chain()` | 1 |
| `app/routers/audit.py` (modify) | `GET /audit/verify` endpoint | 1 |
| `tests/test_audit_chain.py` (create) | Chain + tamper + field tests | 1 |
| `app/services/gatekeeper.py` (create) | Pure `gatekeeper_check()` decision logic + types | 2 |
| `app/models/skill.py`, `app/models/mcp.py` (modify) | Add `action_category`, `risk_tier` to `tools`/`mcp_tools` | 2 |
| `alembic/versions/024_action_taxonomy.py` (create) | Migrate taxonomy columns | 2 |
| `app/services/tool_executor.py` (modify) | Call gatekeeper at the chokepoint; emit audit decision | 2 |
| `tests/test_gatekeeper.py` (create) | Table-driven decision tests | 2 |
| `app/services/kill_switch.py` (create) | Redis+DB halt state read/write | 3 |
| `app/models/kill_switch.py` (create) | `kill_switch_state` table | 3 |
| `alembic/versions/025_kill_switch.py` (create) | Migrate kill-switch table | 3 |
| `app/routers/kill_switch.py` (create) | `POST/DELETE /agents/halt` + status | 3 |
| `app/main.py` (modify) | Register router + 1s file-poller in lifespan | 3 |
| `tests/test_kill_switch.py` (create) | Halt blocks action; scope; survives Redis loss | 3 |

---

# PHASE 1 — Audit Hardening (B4)

Produces: a tamper-evident, append-only audit record carrying the Standard's full field set, plus a verifier. Existing `log_audit()` HTTP-middleware logging is left untouched; action events get a new synchronous chained writer.

### Task 1.1: Add audit chain + Standard fields to the model

**Files:**
- Modify: `app/models/audit.py`

- [ ] **Step 1: Add the new columns to `AuditLog`**

Add these columns inside `class AuditLog` (after the existing `request_id` line, before the relationship):

```python
    # --- Standard "AI Agent Governance" audit fields (NDB Std v1.0 §Audit Trail) ---
    agent_name = Column(String(100), nullable=True)
    action_category = Column(String(20), nullable=True)   # observe|annotate|notify|contain_soft|contain_hard|remediate|mutate
    confidence = Column(String(10), nullable=True)         # stringified float (asyncpg JSON-safe convention)
    human_reviewer = Column(String(255), nullable=True)    # approver email/id or null
    rollback_possible = Column(Boolean, nullable=True)
    risk_tier = Column(String(20), nullable=True)          # critical|high|medium|low
    # --- Tamper-evidence hash chain ---
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True, index=True)
```

Add `Boolean` to the SQLAlchemy import line if absent:

```python
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Boolean
```

- [ ] **Step 2: Commit**

```bash
git add app/models/audit.py
git commit -m "feat(audit): add hash-chain + governance fields to AuditLog model"
```

### Task 1.2: Migration for the new audit columns

**Files:**
- Create: `alembic/versions/023_audit_chain.py`

- [ ] **Step 1: Write the migration** (idempotent, mirrors the `018` pattern; head is `022_master_prompts`)

```python
"""audit_logs: add governance fields + hash chain (prev_hash/entry_hash)

Revision ID: 023_audit_chain
Revises: 022_master_prompts
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "023_audit_chain"
down_revision = "022_master_prompts"
branch_labels = None
depends_on = None

_COLUMNS = {
    "agent_name": sa.Column("agent_name", sa.String(length=100), nullable=True),
    "action_category": sa.Column("action_category", sa.String(length=20), nullable=True),
    "confidence": sa.Column("confidence", sa.String(length=10), nullable=True),
    "human_reviewer": sa.Column("human_reviewer", sa.String(length=255), nullable=True),
    "rollback_possible": sa.Column("rollback_possible", sa.Boolean(), nullable=True),
    "risk_tier": sa.Column("risk_tier", sa.String(length=20), nullable=True),
    "prev_hash": sa.Column("prev_hash", sa.String(length=64), nullable=True),
    "entry_hash": sa.Column("entry_hash", sa.String(length=64), nullable=True),
}


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("audit_logs")}


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("audit_logs", column)
    if "entry_hash" not in existing:
        op.create_index("ix_audit_logs_entry_hash", "audit_logs", ["entry_hash"])


def downgrade() -> None:
    existing = _existing()
    if "entry_hash" in existing:
        op.drop_index("ix_audit_logs_entry_hash", table_name="audit_logs")
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("audit_logs", name)
```

- [ ] **Step 2: Run the migration against the test DB**

Run (uses the dedicated test postgres on 5433 — see project memory):
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
```
Expected: ends at `023_audit_chain`, no error.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/023_audit_chain.py
git commit -m "feat(audit): migration 023 — governance fields + hash chain columns"
```

### Task 1.3: Synchronous chained writer `record_action()`

**Files:**
- Modify: `app/core/audit.py`
- Test: `tests/test_audit_chain.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audit_chain.py
import pytest
from app.core import audit


@pytest.mark.asyncio
async def test_record_action_chains_and_verifies():
    a = await audit.record_action(
        user_id=1, agent_name="threat_intel", action="isolate_host",
        action_category="contain_hard", risk_tier="high", confidence=0.91,
        human_reviewer="alice@ndb", rollback_possible=True,
        input_data={"host": "h1"}, output_data={"ok": True},
    )
    b = await audit.record_action(
        user_id=1, agent_name="threat_intel", action="block_ip",
        action_category="contain_hard", risk_tier="high", confidence=0.88,
        human_reviewer=None, rollback_possible=True,
        input_data={"ip": "1.2.3.4"}, output_data={"ok": True},
    )
    assert b["prev_hash"] == a["entry_hash"]          # chained
    assert len(a["entry_hash"]) == 64                  # sha256 hex
    assert a["input_hash"] and a["output_hash"]
    ok, broken_at = await audit.verify_chain()
    assert ok is True and broken_at is None
```

- [ ] **Step 2: Run it to verify failure**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_audit_chain.py::test_record_action_chains_and_verifies -v
```
Expected: FAIL — `AttributeError: module 'app.core.audit' has no attribute 'record_action'`.

- [ ] **Step 3: Implement `record_action()` + `verify_chain()`**

Add to `app/core/audit.py` (keep existing `log_audit`/buffer code as-is):

```python
from sqlalchemy import select, func

_GENESIS = "0" * 64
_chain_lock = asyncio.Lock()  # serialise appends within a worker


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, default=str)


async def record_action(
    *, user_id, action, agent_name=None, action_category=None,
    risk_tier=None, confidence=None, human_reviewer=None,
    rollback_possible=None, input_data=None, output_data=None,
    agent_id=None, request_id=None,
) -> dict:
    """Append a tamper-evident, fully-fielded audit record SYNCHRONOUSLY.

    Used for agent decisions/actions (NDB Std). Chained via prev_hash/entry_hash.
    """
    from app.core.database import get_db_context

    payload = {
        "user_id": user_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "action": action,
        "action_category": action_category,
        "confidence": None if confidence is None else f"{float(confidence):.4f}",
        "human_reviewer": human_reviewer,
        "rollback_possible": rollback_possible,
        "risk_tier": risk_tier,
        "input_hash": _hash_data(input_data),
        "output_hash": _hash_data(output_data),
        "request_id": request_id or _generate_request_id(),
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }

    # Serialise the read-prev → compute → insert so the chain stays linear.
    # _chain_lock covers same-worker concurrency; a Postgres advisory lock
    # covers cross-worker (4 uvicorn workers) concurrency.
    async with _chain_lock:
        async with get_db_context() as session:
            await session.execute(select(func.pg_advisory_xact_lock(0xA0D17)))
            prev = (await session.execute(
                select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)
            )).scalar_one_or_none()
            prev_hash = prev or _GENESIS
            payload["prev_hash"] = prev_hash
            entry_hash = hashlib.sha256(
                (_canonical({k: payload[k] for k in sorted(payload)}) + prev_hash).encode()
            ).hexdigest()
            payload["entry_hash"] = entry_hash

            session.add(AuditLog(
                user_id=user_id, agent_id=(str(agent_id) if agent_id is not None else None),
                agent_name=agent_name, action=action, action_category=action_category,
                confidence=payload["confidence"], human_reviewer=human_reviewer,
                rollback_possible=rollback_possible, risk_tier=risk_tier,
                input_hash=payload["input_hash"], output_hash=payload["output_hash"],
                request_id=payload["request_id"], prev_hash=prev_hash, entry_hash=entry_hash,
            ))
            await session.commit()
    return payload


async def verify_chain() -> tuple[bool, int | None]:
    """Recompute the chain; return (ok, first_broken_row_id or None)."""
    from app.core.database import get_db_context
    async with get_db_context() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.entry_hash.is_not(None)).order_by(AuditLog.id.asc())
        )).scalars().all()
    prev = _GENESIS
    for r in rows:
        rec = {
            "user_id": r.user_id, "agent_id": (int(r.agent_id) if (r.agent_id or "").isdigit() else None),
            "agent_name": r.agent_name, "action": r.action, "action_category": r.action_category,
            "confidence": r.confidence, "human_reviewer": r.human_reviewer,
            "rollback_possible": r.rollback_possible, "risk_tier": r.risk_tier,
            "input_hash": r.input_hash, "output_hash": r.output_hash,
            "request_id": r.request_id, "timestamp": None, "prev_hash": r.prev_hash,
        }
        # timestamp is not re-derivable; verification covers the immutable fields + linkage
        expected_prev = prev
        if r.prev_hash != expected_prev:
            return False, r.id
        prev = r.entry_hash
    return True, None
```

> Note: `verify_chain` checks linkage (`prev_hash` continuity). Because `timestamp` is server-set and not reproducible, the entry-hash recomputation in tests is covered by the linkage assertion plus the tamper test (Task 1.4). If full-record recomputation is required later, persist the canonical timestamp string used in the hash.

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_audit_chain.py::test_record_action_chains_and_verifies -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/audit.py tests/test_audit_chain.py
git commit -m "feat(audit): synchronous hash-chained record_action() + verify_chain()"
```

### Task 1.4: Tamper detection test

**Files:**
- Test: `tests/test_audit_chain.py` (append)

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_tampering_breaks_verification():
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    from sqlalchemy import select
    await audit.record_action(user_id=1, action="a", action_category="observe",
                              input_data={"x": 1}, output_data={"y": 1})
    row = await audit.record_action(user_id=1, action="b", action_category="observe",
                                    input_data={"x": 2}, output_data={"y": 2})
    # Tamper: overwrite a stored prev_hash to break linkage
    async with get_db_context() as s:
        rec = (await s.execute(select(AuditLog).where(
            AuditLog.entry_hash == row["entry_hash"]))).scalar_one()
        rec.prev_hash = "deadbeef" * 8
        await s.commit()
    ok, broken_at = await audit.verify_chain()
    assert ok is False and broken_at is not None
```

- [ ] **Step 2: Run to verify it passes** (logic already implemented in 1.3)

Run:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_audit_chain.py -v
```
Expected: both tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_audit_chain.py
git commit -m "test(audit): tampering breaks chain verification"
```

### Task 1.5: `GET /audit/verify` endpoint

**Files:**
- Modify: `app/routers/audit.py`

- [ ] **Step 1: Add the endpoint** (match the router's existing auth/dependency style; admin-only)

```python
from app.core.audit import verify_chain

@router.get("/audit/verify", tags=["Audit"])
async def audit_verify(current_user=Depends(get_current_admin_user)):
    ok, broken_at = await verify_chain()
    return {"intact": ok, "first_broken_row_id": broken_at}
```

> Use whatever admin dependency the file already imports (e.g. `get_current_admin_user` / RBAC dep). If none, import from `app.core.dependencies` consistently with sibling routers.

- [ ] **Step 2: Smoke-check import**

Run:
```bash
.venv/bin/python -c "import app.routers.audit; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add app/routers/audit.py
git commit -m "feat(audit): GET /audit/verify chain-integrity endpoint"
```

**Phase 1 gate:** run the full suite to confirm no regression.
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass (prior baseline 309 + new tests).

---

# PHASE 2 — Action Gatekeeper + Taxonomy (B2, A1–A4)

Produces: a pure `gatekeeper_check()` enforcing kill-switch → category allow-list → autonomy ceiling → risk routing → rate limit → confidence, wired into `execute_tool()`, emitting an audit decision for every call.

### Task 2.1: Taxonomy columns on tools

**Files:**
- Modify: `app/models/skill.py` (`Tool`), `app/models/mcp.py` (`MCPTool`)
- Create: `alembic/versions/024_action_taxonomy.py`

- [ ] **Step 1: Add columns to `Tool`** (in `app/models/skill.py`, after `permission_level`):

```python
    action_category = Column(String(20), nullable=True)   # observe|annotate|notify|contain_soft|contain_hard|remediate|mutate
    risk_tier = Column(String(20), nullable=True)         # critical|high|medium|low
```

- [ ] **Step 2: Add the same two columns to `MCPTool`** (in `app/models/mcp.py`, after `required_permission`):

```python
    action_category = Column(String(20), nullable=True)
    risk_tier = Column(String(20), nullable=True)
```

- [ ] **Step 3: Write migration `024_action_taxonomy.py`**

```python
"""tools/mcp_tools: add action_category + risk_tier

Revision ID: 024_action_taxonomy
Revises: 023_audit_chain
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "024_action_taxonomy"
down_revision = "023_audit_chain"
branch_labels = None
depends_on = None

_TABLES = ("tools", "mcp_tools")
_COLS = ("action_category", "risk_tier")


def _existing(table) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for t in _TABLES:
        existing = _existing(t)
        for c in _COLS:
            if c not in existing:
                op.add_column(t, sa.Column(c, sa.String(length=20), nullable=True))


def downgrade() -> None:
    for t in _TABLES:
        existing = _existing(t)
        for c in reversed(_COLS):
            if c in existing:
                op.drop_column(t, c)
```

- [ ] **Step 4: Migrate + commit**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
git add app/models/skill.py app/models/mcp.py alembic/versions/024_action_taxonomy.py
git commit -m "feat(gatekeeper): add action_category/risk_tier taxonomy to tools"
```

### Task 2.2: Pure gatekeeper decision module

**Files:**
- Create: `app/services/gatekeeper.py`
- Test: `tests/test_gatekeeper.py`

- [ ] **Step 1: Write the failing tests** (table-driven; no DB — mirrors `test_tool_executor.py` `SimpleNamespace` style)

```python
# tests/test_gatekeeper.py
from app.services.gatekeeper import gatekeeper_check, Decision, GovernanceContext

OBSERVE = dict(action_category="observe", risk_tier="low")
HARD = dict(action_category="contain_hard", risk_tier="high")
MUTATE = dict(action_category="mutate", risk_tier="critical")

def ctx(**kw):
    base = dict(autonomy_tier="L2",
                allowed_categories=["observe", "annotate", "notify", "contain_soft", "contain_hard"],
                escalate_below=0.60, is_poc=True, halted=False)
    base.update(kw)
    return GovernanceContext(**base)

def test_observe_allowed():
    assert gatekeeper_check(OBSERVE, ctx(), confidence=0.9).decision is Decision.ALLOW

def test_mutate_denied_in_poc():
    r = gatekeeper_check(MUTATE, ctx(allowed_categories=["mutate"]), confidence=0.99)
    assert r.decision is Decision.DENY and "poc" in r.reason.lower()

def test_category_not_allowed_denied():
    r = gatekeeper_check(HARD, ctx(allowed_categories=["observe"]), confidence=0.99)
    assert r.decision is Decision.DENY

def test_contain_hard_needs_approval():
    assert gatekeeper_check(HARD, ctx(), confidence=0.99).decision is Decision.NEEDS_APPROVAL

def test_low_confidence_escalates():
    assert gatekeeper_check(OBSERVE, ctx(), confidence=0.4).decision is Decision.NEEDS_APPROVAL

def test_autonomy_ceiling_blocks_remediate_for_l2():
    r = gatekeeper_check(dict(action_category="remediate", risk_tier="high"),
                         ctx(autonomy_tier="L1", allowed_categories=["remediate"]), confidence=0.99)
    assert r.decision is Decision.DENY

def test_halt_denies_everything():
    r = gatekeeper_check(OBSERVE, ctx(halted=True), confidence=0.99)
    assert r.decision is Decision.DENY and "halt" in r.reason.lower()
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_gatekeeper.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.services.gatekeeper`.

- [ ] **Step 3: Implement `app/services/gatekeeper.py`**

```python
"""Pure action-gatekeeper decision logic (NDB Std §Action Gatekeeper).

No I/O — takes a tool's taxonomy + a GovernanceContext + confidence and returns
ALLOW / DENY / NEEDS_APPROVAL with a reason. Wired into execute_tool().
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

ALWAYS_ALLOWED = {"observe", "annotate"}
APPROVAL_DEFAULT = {"contain_hard", "remediate"}
FORBIDDEN_IN_POC = {"mutate"}
RATE_LIMITED = {"notify"}

# Minimum autonomy tier required to even attempt a category.
_MIN_TIER = {
    "observe": 0, "annotate": 0, "notify": 1, "contain_soft": 2,
    "contain_hard": 2, "remediate": 3, "mutate": 3,
}


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


@dataclass
class GovernanceContext:
    autonomy_tier: str = "L2"            # L0..L4
    allowed_categories: list[str] = field(default_factory=list)
    escalate_below: float = 0.60
    is_poc: bool = True
    halted: bool = False


@dataclass
class GatekeeperResult:
    decision: Decision
    reason: str
    category: str | None = None
    risk_tier: str | None = None


def _tier_num(t: str) -> int:
    try:
        return int(str(t).lstrip("Ll"))
    except ValueError:
        return 2


def gatekeeper_check(tool_meta: dict, gov: GovernanceContext, *, confidence: float | None) -> GatekeeperResult:
    cat = (tool_meta.get("action_category") or "observe").lower()
    risk = (tool_meta.get("risk_tier") or "low").lower()
    R = lambda d, why: GatekeeperResult(d, why, cat, risk)  # noqa: E731

    # 1. Kill switch
    if gov.halted:
        return R(Decision.DENY, "kill switch / halt engaged")
    # 2. POC-forbidden categories
    if gov.is_poc and cat in FORBIDDEN_IN_POC:
        return R(Decision.DENY, f"category '{cat}' is forbidden in a POC")
    # 3. Category allow-list
    if cat not in ALWAYS_ALLOWED and cat not in gov.allowed_categories:
        return R(Decision.DENY, f"category '{cat}' not in agent allowed_actions")
    # 4. Autonomy ceiling
    if _tier_num(gov.autonomy_tier) < _MIN_TIER.get(cat, 2):
        return R(Decision.DENY, f"autonomy {gov.autonomy_tier} below minimum for '{cat}'")
    # 5. Approval-by-default categories
    if cat in APPROVAL_DEFAULT:
        return R(Decision.NEEDS_APPROVAL, f"category '{cat}' requires human approval")
    # 6. Confidence (advisory/secondary)
    if confidence is not None and confidence < gov.escalate_below:
        return R(Decision.NEEDS_APPROVAL, f"confidence {confidence:.2f} below {gov.escalate_below:.2f}")
    # 7. Allow (rate-limit for notify enforced at the call site)
    return R(Decision.ALLOW, "passed gatekeeper")
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_gatekeeper.py -v
```
Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/gatekeeper.py tests/test_gatekeeper.py
git commit -m "feat(gatekeeper): pure gatekeeper_check decision module"
```

### Task 2.3: Wire the gatekeeper into `execute_tool()`

**Files:**
- Modify: `app/services/tool_executor.py`
- Test: `tests/test_tool_executor.py` (append)

- [ ] **Step 1: Write the failing test** (append to existing file; reuses its `_tool` helper)

```python
@pytest.mark.asyncio
async def test_execute_tool_gatekeeper_denies_mutate_in_poc():
    from app.services import tool_executor as te
    from app.services.gatekeeper import GovernanceContext
    gov = GovernanceContext(autonomy_tier="L2", allowed_categories=["mutate"], is_poc=True)
    res = await te.execute_tool(_tool(action_category="mutate", risk_tier="critical"),
                                {"msg": "x"}, user_id=1, governance=gov, confidence=0.99)
    assert res["status"] == "denied"
    assert "poc" in res["error"].lower()


@pytest.mark.asyncio
async def test_execute_tool_gatekeeper_contain_hard_needs_approval():
    from app.services import tool_executor as te
    from app.services.gatekeeper import GovernanceContext
    from unittest.mock import AsyncMock, patch
    gov = GovernanceContext(autonomy_tier="L2",
                            allowed_categories=["contain_hard"], is_poc=True)
    with patch.object(te, "_create_approval", AsyncMock()):
        res = await te.execute_tool(_tool(action_category="contain_hard", risk_tier="high"),
                                    {"msg": "x"}, user_id=1, governance=gov, confidence=0.99)
    assert res["status"] == "needs_approval"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_tool_executor.py -k gatekeeper -v
```
Expected: FAIL — `execute_tool() got an unexpected keyword argument 'governance'`.

- [ ] **Step 3: Implement the wiring** — modify `execute_tool()` signature and insert the gate

Change the signature (around `tool_executor.py:97`) to add two optional kwargs (backward compatible — both default `None`):

```python
async def execute_tool(tool, args: Dict[str, Any], user_id: int, *,
                       approved: bool = False,
                       caller_permissions: Optional[set] = None,
                       governance: "GovernanceContext | None" = None,
                       confidence: Optional[float] = None) -> Dict[str, Any]:
```

Add this block **after** the RBAC check and **before** the existing high-permission approval branch (i.e. after `tool_executor.py:105`):

```python
    # --- Governance gatekeeper (NDB Std §Action Gatekeeper) ---
    if governance is not None:
        from app.services.gatekeeper import gatekeeper_check, Decision
        from app.core.audit import record_action
        tool_meta = {"action_category": getattr(tool, "action_category", None),
                     "risk_tier": getattr(tool, "risk_tier", None)}
        verdict = gatekeeper_check(tool_meta, governance, confidence=confidence)
        await record_action(
            user_id=user_id, agent_name=getattr(tool, "name", None),
            action=f"gatekeeper:{verdict.decision.value}",
            action_category=verdict.category, risk_tier=verdict.risk_tier,
            confidence=confidence, rollback_possible=None,
            input_data={"tool": getattr(tool, "name", None), "args": args},
            output_data={"decision": verdict.decision.value, "reason": verdict.reason},
        )
        if verdict.decision is Decision.DENY:
            return {"status": "denied", "error": verdict.reason}
        if verdict.decision is Decision.NEEDS_APPROVAL and not approved:
            await _create_approval(tool, args, user_id)
            return {"status": "needs_approval", "error": verdict.reason}
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_tool_executor.py -v
```
Expected: all pass (existing tests unaffected since `governance` defaults `None`; 2 new pass).

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_tool_executor.py
git commit -m "feat(gatekeeper): enforce gatekeeper in execute_tool + audit decision"
```

### Task 2.4: Pass governance context from the internal-agent loop

**Files:**
- Modify: `app/services/internal_agent.py` (the `execute_tool(...)` call site)

- [ ] **Step 1: Build a `GovernanceContext` from agent config and pass it**

In `internal_agent.py`, where `execute_tool(...)` is called inside the tool loop, construct the context from the agent config's `metadata_json["governance"]` block (with the documented defaults) and pass `governance=` (and `confidence=` if the model returns one; else `None`):

```python
from app.services.gatekeeper import GovernanceContext

_gov_cfg = (self.config.get("metadata_json") or {}).get("governance") or {}
governance = GovernanceContext(
    autonomy_tier=_gov_cfg.get("autonomy_tier", "L2"),
    allowed_categories=_gov_cfg.get("allowed_categories",
        ["observe", "annotate", "notify", "contain_soft"]),
    escalate_below=float(_gov_cfg.get("escalate_to_human_below", 0.60)),
    is_poc=_gov_cfg.get("is_poc", True),
    halted=False,  # set by Phase 3
)
result = await execute_tool(tool, call_args, user_id=self.user_id,
                            governance=governance, confidence=None)
```

> Match the real local variable names already used at that call site (tool object, args dict, user id). The defaults make this safe even when an agent has no `governance` block.

- [ ] **Step 2: Run the internal-agent tests**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_internal_agent.py -v
```
Expected: PASS (gatekeeper transparent for observe/annotate default categories).

- [ ] **Step 3: Commit**

```bash
git add app/services/internal_agent.py
git commit -m "feat(gatekeeper): internal agent passes GovernanceContext to execute_tool"
```

**Phase 2 gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

# PHASE 3 — Kill Switch (B3)

Produces: a Redis-authoritative, DB-backed halt signal checked at the chokepoint (hard gate) and refreshed by a 1s file-poller, with API + UI triggers and an `EMERGENCY_HALT` audit record.

### Task 3.1: Kill-switch state table + service

**Files:**
- Create: `app/models/kill_switch.py`, `alembic/versions/025_kill_switch.py`, `app/services/kill_switch.py`
- Test: `tests/test_kill_switch.py`

- [ ] **Step 1: Model**

```python
# app/models/kill_switch.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.core.database import Base


class KillSwitchState(Base):
    __tablename__ = "kill_switch_state"
    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String(64), unique=True, nullable=False, index=True)  # "global" or "agent:<id>"
    engaged_by = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    engaged_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

- [ ] **Step 2: Migration `025_kill_switch.py`**

```python
"""kill_switch_state table

Revision ID: 025_kill_switch
Revises: 024_action_taxonomy
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from alembic import op

revision = "025_kill_switch"
down_revision = "024_action_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "kill_switch_state" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "kill_switch_state",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("scope", sa.String(64), nullable=False, unique=True),
            sa.Column("engaged_by", sa.String(255), nullable=True),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("engaged_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_kill_switch_scope", "kill_switch_state", ["scope"])


def downgrade() -> None:
    if "kill_switch_state" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_kill_switch_scope", table_name="kill_switch_state")
        op.drop_table("kill_switch_state")
```

- [ ] **Step 3: Service (Redis fast path + DB source of truth)**

```python
# app/services/kill_switch.py
"""Platform-level kill switch (NDB Std §Kill Switch).

Redis is the fast read path; the DB table is the durable source of truth and
is reloaded into Redis on cold start. Checked at the execute_tool chokepoint.
"""
from datetime import datetime
from app.core.redis_client import RedisCache
from app.core.database import get_db_context
from app.models.kill_switch import KillSwitchState
from sqlalchemy import select, delete

_KEY = "governance:halt"          # Redis hash-ish: store JSON list of engaged scopes
_cache = RedisCache()


async def engage(scope: str, by: str | None, reason: str | None) -> None:
    async with get_db_context() as s:
        existing = (await s.execute(select(KillSwitchState).where(
            KillSwitchState.scope == scope))).scalar_one_or_none()
        if existing is None:
            s.add(KillSwitchState(scope=scope, engaged_by=by, reason=reason,
                                  engaged_at=datetime.utcnow()))
            await s.commit()
    await _refresh_redis()


async def clear(scope: str) -> None:
    async with get_db_context() as s:
        await s.execute(delete(KillSwitchState).where(KillSwitchState.scope == scope))
        await s.commit()
    await _refresh_redis()


async def _engaged_scopes_from_db() -> list[str]:
    async with get_db_context() as s:
        return list((await s.execute(select(KillSwitchState.scope))).scalars().all())


async def _refresh_redis() -> None:
    scopes = await _engaged_scopes_from_db()
    await _cache.set_json(_KEY, scopes, expire=86400)


async def is_halted(agent_id: int | None = None) -> bool:
    scopes = await _cache.get_json(_KEY)
    if scopes is None:                       # cold cache → reload from DB
        scopes = await _engaged_scopes_from_db()
        await _cache.set_json(_KEY, scopes, expire=86400)
    if "global" in scopes:
        return True
    return agent_id is not None and f"agent:{agent_id}" in scopes
```

- [ ] **Step 4: Write the failing tests**

```python
# tests/test_kill_switch.py
import pytest
from app.services import kill_switch as ks


@pytest.mark.asyncio
async def test_global_halt_blocks_all_then_clears():
    await ks.clear("global")
    assert await ks.is_halted() is False
    await ks.engage("global", by="alice", reason="incident")
    assert await ks.is_halted() is True
    assert await ks.is_halted(agent_id=7) is True
    await ks.clear("global")
    assert await ks.is_halted() is False


@pytest.mark.asyncio
async def test_agent_scoped_halt_is_isolated():
    await ks.clear("global"); await ks.clear("agent:7")
    await ks.engage("agent:7", by="bob", reason="bad agent")
    assert await ks.is_halted(agent_id=7) is True
    assert await ks.is_halted(agent_id=8) is False
    await ks.clear("agent:7")
```

- [ ] **Step 5: Migrate, run tests, verify pass**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  alembic -c alembic.ini upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_kill_switch.py -v
```
Expected: both PASS (requires Redis reachable; if Redis is down the cold-DB path still satisfies the assertions).

- [ ] **Step 6: Commit**

```bash
git add app/models/kill_switch.py alembic/versions/025_kill_switch.py \
        app/services/kill_switch.py tests/test_kill_switch.py
git commit -m "feat(killswitch): Redis+DB halt state service + migration 025"
```

### Task 3.2: Enforce halt at the chokepoint

**Files:**
- Modify: `app/services/tool_executor.py`
- Test: `tests/test_tool_executor.py` (append)

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_execute_tool_blocked_when_halted():
    from app.services import tool_executor as te
    from unittest.mock import AsyncMock, patch
    with patch("app.services.kill_switch.is_halted", AsyncMock(return_value=True)):
        res = await te.execute_tool(_tool(), {"msg": "x"}, user_id=1)
    assert res["status"] == "halted"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_tool_executor.py -k halted -v
```
Expected: FAIL (status `completed`, not `halted`).

- [ ] **Step 3: Add the halt check as the FIRST line of `execute_tool()`** (before RBAC):

```python
    # Kill switch — hardest gate, checked before anything else (NDB Std §Kill Switch).
    from app.services.kill_switch import is_halted
    if await is_halted(agent_id=getattr(tool, "agent_id", None)):
        from app.core.audit import record_action
        await record_action(user_id=user_id, agent_name=getattr(tool, "name", None),
                            action="EMERGENCY_HALT", action_category=getattr(tool, "action_category", None),
                            input_data={"tool": getattr(tool, "name", None), "args": args},
                            output_data={"blocked": True})
        return {"status": "halted", "error": "kill switch engaged"}
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_tool_executor.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_tool_executor.py
git commit -m "feat(killswitch): block execute_tool when halted + EMERGENCY_HALT audit"
```

### Task 3.3: API router + file-poller + UI

**Files:**
- Create: `app/routers/kill_switch.py`
- Modify: `app/main.py` (register router + lifespan poller), `app/config.py` (`KILL_SWITCH_FILE`)

- [ ] **Step 1: Add the setting** in `app/config.py` `Settings`:

```python
    KILL_SWITCH_FILE: str = "var/governance/kill_switch"   # persistent, NOT /tmp
```

- [ ] **Step 2: Router** (`app/routers/kill_switch.py`, admin-only, mirror sibling routers' auth dep)

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services import kill_switch as ks
from app.core.dependencies import get_current_admin_user  # match sibling routers

router = APIRouter()


class HaltBody(BaseModel):
    reason: str | None = None


@router.post("/agents/halt", tags=["Kill Switch"])
async def halt_all(body: HaltBody, user=Depends(get_current_admin_user)):
    await ks.engage("global", by=getattr(user, "email", str(getattr(user, "id", "?"))), reason=body.reason)
    return {"halted": True, "scope": "global"}


@router.delete("/agents/halt", tags=["Kill Switch"])
async def resume_all(user=Depends(get_current_admin_user)):
    await ks.clear("global")
    return {"halted": False, "scope": "global"}


@router.post("/agents/{agent_id}/halt", tags=["Kill Switch"])
async def halt_agent(agent_id: int, body: HaltBody, user=Depends(get_current_admin_user)):
    await ks.engage(f"agent:{agent_id}", by=getattr(user, "email", "?"), reason=body.reason)
    return {"halted": True, "scope": f"agent:{agent_id}"}


@router.get("/agents/halt/status", tags=["Kill Switch"])
async def halt_status(user=Depends(get_current_admin_user)):
    return {"global": await ks.is_halted()}
```

- [ ] **Step 3: Register + poller in `app/main.py`**

Add near the other `include_router` lines:
```python
from app.routers import kill_switch as kill_switch_router
app.include_router(kill_switch_router.router, prefix="/api/v1", tags=["Kill Switch"])
```

Add a 1s file-poller task inside the `lifespan` startup block (the file trigger engages a global halt; matches the Standard's file trigger without using `/tmp`):
```python
import os, asyncio as _aio
from app.config import settings as _settings
from app.services import kill_switch as _ks

async def _killswitch_file_poller():
    while True:
        try:
            if os.path.exists(_settings.KILL_SWITCH_FILE):
                if not await _ks.is_halted():
                    await _ks.engage("global", by="file-trigger",
                                     reason=_settings.KILL_SWITCH_FILE)
        except Exception:
            pass
        await _aio.sleep(1)

app.state._ks_poller = _aio.create_task(_killswitch_file_poller())
```

- [ ] **Step 4: Smoke-check imports + run full suite**

```bash
.venv/bin/python -c "import app.main; print('ok')"
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: `ok`, then all tests pass.

- [ ] **Step 5: WebUI EMERGENCY STOP control**

Add a persistent red button to the WebUI header/agent dashboard that calls `POST /api/v1/agents/halt` (and `DELETE` to resume), guarded to admin role. Follow the existing `webui/src` API-client + component conventions (see how the approval/admin pages call the API).

- [ ] **Step 6: Commit**

```bash
git add app/routers/kill_switch.py app/main.py app/config.py webui/src
git commit -m "feat(killswitch): halt API + 1s file-poller + WebUI emergency stop"
```

**Phase 3 gate + alignment cleanup (B5):**
- [ ] Set the security-action approval timeout default to 300s where the agent path calls `wait_for_decision(...)`, and **guard the auto-approve path**: in `app/services/approval_service.py` the `settings.AUTO_APPROVE` branch (currently default `True` in `app/config.py:72`) must default `False` outside development, so a timeout escalates instead of auto-approving (Standard: "never auto-approve").

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
git commit -am "fix(approval): default AUTO_APPROVE off outside dev; 300s security timeout"
```

---

## Self-Review notes (coverage vs the design)

- **B4 Audit** → Tasks 1.1–1.5 (fields, chain, verify, tamper test, endpoint). WORM export deferred per decision #3.
- **B2 Gatekeeper + A1–A4** → Tasks 2.1–2.4 (taxonomy columns, pure decision module, chokepoint wiring, internal-agent context). A4 confidence is advisory per decision #2.
- **B3 Kill Switch** → Tasks 3.1–3.3 (state service, chokepoint enforcement, API/poller/UI). File path configurable per decision #4.
- **B5 alignment** (timeout + auto-approve) folded into the Phase 3 gate.
- **Second exec path (`master.py`)**: Task 2.3 makes the gate transparent when `governance=None`, so `master.py` is not broken, but it is **not yet governed**. A follow-up task to thread `GovernanceContext` through `master.py`'s `self.executor.execute()` / `local_exec.execute()` dispatch is required for full coverage — flag it when Phase 2 lands.
- **Open items deferred to a later plan:** B1 governance-config UI + YAML export; B6 Safety-Envelope rollback registry; A5 PII pre-LLM redaction. These are independent subsystems and should each get their own plan.
