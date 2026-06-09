# POC Governance Evidence & Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the Standard's §5 *POC Governance Requirements* — the deliverable artifacts NDB IT Security checks at POC sign-off, plus a live governance-metrics report that proves the Success Criteria (governance-violation rate < 0.5%, human-override rate < 10% of L2, kill-switch < 3s, audit completeness 100%, rollback success > 99%).

**Architecture:** A read-only `governance_metrics` service computes each metric from data the earlier plans already write — gatekeeper decisions and `EMERGENCY_HALT`/`pii_redaction` events in the audit chain, approval outcomes, and rollback registrations. A `GET /governance/metrics` endpoint returns each metric with its target and pass/fail. A **red-team governance test suite** doubles as the `governance_tests.md` deliverable by asserting every forbidden path is blocked. Static deliverable docs (`audit_schema.md`, `scripts/rollbacks/`) round out the §5 checklist; `agent_governance.yaml` is already produced by the governance-config plan's export.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest. Read-only — **no DB migration**.

---

## Dependencies & decisions

- **Depends on all four prior governance plans** (controls / governance-config / pii / safety-envelope). The metrics query the data those plans emit:
  - gatekeeper decisions → audit rows with `action LIKE 'gatekeeper:%'` (Phase-2 `record_action`).
  - kill-switch → `EMERGENCY_HALT` audit rows + `kill_switch_state.engaged_at`.
  - approvals → `approval_requests.status` + `risk_level`.
  - rollbacks → `rollback_registrations.status`.
  - audit completeness → `verify_chain()` (Phase-1).
- **Metric definitions** (operationalising the Standard's prose):
  | Metric | Definition | Target |
  |--------|-----------|--------|
  | governance_violation_rate | `DENY` decisions ÷ total gatekeeper decisions | < 0.5% |
  | human_override_rate | `rejected` approvals ÷ total approval decisions | < 10% |
  | kill_switch_response_seconds | synthetic probe: engage→`is_halted()` true | < 3s |
  | audit_completeness | `verify_chain()` intact ? 100% : <100% | 100% |
  | rollback_success_rate | `reverted` ÷ (`reverted`+`failed`) | > 99% |
- **Window:** metrics computed over a rolling window (default 30 days), configurable via query param.

## File Structure

| File | Responsibility |
|------|----------------|
| `app/services/governance_metrics.py` (create) | Read-only metric computations + targets/verdicts |
| `app/routers/governance_metrics.py` (create) | `GET /governance/metrics` |
| `app/main.py` (modify) | Register the router |
| `tests/test_governance_metrics.py` (create) | Metric math + verdict tests |
| `tests/test_governance_redteam.py` (create) | Red-team: every forbidden path is blocked (= deliverable evidence) |
| `docs/governance/audit_schema.md` (create) | §5 deliverable: audit record schema |
| `docs/governance/governance_tests.md` (create) | §5 deliverable: red-team results narrative |
| `scripts/rollbacks/README.md` (create) | §5 deliverable: rollback procedure conventions |

---

### Task 1: Governance metrics service

**Files:**
- Create: `app/services/governance_metrics.py`
- Test: `tests/test_governance_metrics.py`

- [ ] **Step 1: Write the failing tests** (pure verdict math is DB-free; DB-backed counts are mocked)

```python
# tests/test_governance_metrics.py
import pytest
from unittest.mock import AsyncMock, patch
from app.services import governance_metrics as gm


def test_verdict_pass_fail():
    assert gm._verdict("governance_violation_rate", 0.004) is True    # < 0.5%
    assert gm._verdict("governance_violation_rate", 0.02) is False
    assert gm._verdict("kill_switch_response_seconds", 1.2) is True   # < 3s
    assert gm._verdict("kill_switch_response_seconds", 4.0) is False
    assert gm._verdict("rollback_success_rate", 0.995) is True        # > 99%
    assert gm._verdict("audit_completeness", 1.0) is True
    assert gm._verdict("audit_completeness", 0.99) is False


def test_rate_helpers():
    assert gm._rate(0, 0) == 0.0           # no data → 0, not div-by-zero
    assert gm._rate(1, 200) == 0.005


@pytest.mark.asyncio
async def test_collect_assembles_all_metrics():
    with patch.object(gm, "_governance_violation_rate", AsyncMock(return_value=0.004)), \
         patch.object(gm, "_human_override_rate", AsyncMock(return_value=0.05)), \
         patch.object(gm, "_kill_switch_response", AsyncMock(return_value=0.8)), \
         patch.object(gm, "_audit_completeness", AsyncMock(return_value=1.0)), \
         patch.object(gm, "_rollback_success_rate", AsyncMock(return_value=1.0)):
        report = await gm.collect(window_days=30)
    names = {m["name"] for m in report["metrics"]}
    assert names == {"governance_violation_rate", "human_override_rate",
                     "kill_switch_response_seconds", "audit_completeness",
                     "rollback_success_rate"}
    assert report["all_pass"] is True
    assert all("target" in m and "pass" in m for m in report["metrics"])
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_governance_metrics.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.services.governance_metrics`.

- [ ] **Step 3: Implement `app/services/governance_metrics.py`**

```python
"""Read-only governance metrics (NDB Std §POC Success Criteria)."""
from __future__ import annotations
import time
from datetime import datetime, timedelta
from sqlalchemy import select, func

# name → (target value, comparator) ; comparator(value, target) -> bool
_TARGETS = {
    "governance_violation_rate":    (0.005, lambda v, t: v < t),
    "human_override_rate":          (0.10,  lambda v, t: v < t),
    "kill_switch_response_seconds": (3.0,   lambda v, t: v < t),
    "audit_completeness":           (1.0,   lambda v, t: v >= t),
    "rollback_success_rate":        (0.99,  lambda v, t: v > t),
}


def _verdict(name: str, value: float) -> bool:
    target, cmp = _TARGETS[name]
    return cmp(value, target)


def _rate(num: int, denom: int) -> float:
    return 0.0 if denom == 0 else num / denom


def _since(window_days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=window_days)


async def _governance_violation_rate(window_days: int) -> float:
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    since = _since(window_days)
    async with get_db_context() as s:
        total = (await s.execute(select(func.count()).select_from(AuditLog).where(
            AuditLog.action.like("gatekeeper:%"), AuditLog.timestamp >= since))).scalar() or 0
        denied = (await s.execute(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "gatekeeper:deny", AuditLog.timestamp >= since))).scalar() or 0
    return _rate(denied, total)


async def _human_override_rate(window_days: int) -> float:
    from app.core.database import get_db_context
    from app.models.approval import ApprovalRequest
    since = _since(window_days)
    async with get_db_context() as s:
        decided = (await s.execute(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.status.in_(("approved", "rejected")),
            ApprovalRequest.created_at >= since))).scalar() or 0
        rejected = (await s.execute(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.status == "rejected", ApprovalRequest.created_at >= since))).scalar() or 0
    return _rate(rejected, decided)


async def _kill_switch_response(window_days: int) -> float:
    """Synthetic probe: time from engage() to is_halted() reflecting it."""
    from app.services import kill_switch as ks
    probe = "agent:__metrics_probe__"
    await ks.clear(probe)
    t0 = time.monotonic()
    await ks.engage(probe, by="metrics", reason="response probe")
    elapsed = 99.0
    for _ in range(60):                       # up to ~3s, 50ms steps
        if await ks.is_halted(agent_id="__metrics_probe__"):
            elapsed = time.monotonic() - t0
            break
        time.sleep(0.05)
    await ks.clear(probe)
    return round(elapsed, 3)


async def _audit_completeness(window_days: int) -> float:
    from app.core.audit import verify_chain
    ok, _ = await verify_chain()
    return 1.0 if ok else 0.0


async def _rollback_success_rate(window_days: int) -> float:
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    since = _since(window_days)
    async with get_db_context() as s:
        reverted = (await s.execute(select(func.count()).select_from(RollbackRegistration).where(
            RollbackRegistration.status == "reverted", RollbackRegistration.created_at >= since))).scalar() or 0
        failed = (await s.execute(select(func.count()).select_from(RollbackRegistration).where(
            RollbackRegistration.status == "failed", RollbackRegistration.created_at >= since))).scalar() or 0
    total = reverted + failed
    return 1.0 if total == 0 else _rate(reverted, total)


async def collect(window_days: int = 30) -> dict:
    values = {
        "governance_violation_rate":    await _governance_violation_rate(window_days),
        "human_override_rate":          await _human_override_rate(window_days),
        "kill_switch_response_seconds": await _kill_switch_response(window_days),
        "audit_completeness":           await _audit_completeness(window_days),
        "rollback_success_rate":        await _rollback_success_rate(window_days),
    }
    metrics = [{"name": n, "value": v, "target": _TARGETS[n][0], "pass": _verdict(n, v)}
               for n, v in values.items()]
    return {"window_days": window_days, "metrics": metrics,
            "all_pass": all(m["pass"] for m in metrics)}
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_governance_metrics.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/governance_metrics.py tests/test_governance_metrics.py
git commit -m "feat(metrics): governance metrics service (POC success criteria)"
```

### Task 2: Metrics endpoint

**Files:**
- Create: `app/routers/governance_metrics.py`
- Modify: `app/main.py`

- [ ] **Step 1: Router**

```python
# app/routers/governance_metrics.py
from fastapi import APIRouter, Depends
from app.core.rbac import Permission, require_permission
from app.services.governance_metrics import collect

router = APIRouter()


@router.get("/governance/metrics")
async def governance_metrics(window_days: int = 30,
                             _=Depends(require_permission(Permission.SETTINGS_READ))):
    return await collect(window_days=window_days)
```

- [ ] **Step 2: Register in `app/main.py`**

```python
from app.routers import governance_metrics as governance_metrics_router
app.include_router(governance_metrics_router.router, prefix="/api/v1", tags=["Governance Metrics"])
```

- [ ] **Step 3: Smoke-check + commit**

```bash
.venv/bin/python -c "import app.main; print('ok')"
git add app/routers/governance_metrics.py app/main.py
git commit -m "feat(metrics): GET /governance/metrics endpoint"
```

### Task 3: Red-team governance test suite (= §5 deliverable evidence)

**Files:**
- Create: `tests/test_governance_redteam.py`

- [ ] **Step 1: Write the suite** — each test asserts a forbidden path is blocked. These are the machine-checkable evidence behind `governance_tests.md`.

```python
# tests/test_governance_redteam.py
"""Red-team governance tests — every forbidden path must be blocked.
Machine-checkable evidence for the POC 'Governance test results' deliverable."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services.gatekeeper import gatekeeper_check, Decision, GovernanceContext
from app.core import pii


def _ctx(**kw):
    base = dict(autonomy_tier="L2",
                allowed_categories=["observe", "annotate", "notify", "contain_soft", "contain_hard"],
                escalate_below=0.60, is_poc=True, halted=False)
    base.update(kw)
    return GovernanceContext(**base)


def test_redteam_mutate_blocked_in_poc():
    r = gatekeeper_check({"action_category": "mutate", "risk_tier": "critical"},
                         _ctx(allowed_categories=["mutate"]), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_action_above_autonomy_blocked():
    r = gatekeeper_check({"action_category": "remediate", "risk_tier": "high", "has_rollback": True},
                         _ctx(autonomy_tier="L1", allowed_categories=["remediate"]), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_contain_without_rollback_blocked():
    r = gatekeeper_check({"action_category": "contain_hard", "risk_tier": "high", "has_rollback": False},
                         _ctx(), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_low_confidence_escalated():
    r = gatekeeper_check({"action_category": "contain_soft", "risk_tier": "low", "has_rollback": True},
                         _ctx(), confidence=0.30)
    assert r.decision is Decision.NEEDS_APPROVAL


def test_redteam_halt_blocks_everything():
    r = gatekeeper_check({"action_category": "observe", "risk_tier": "low"},
                         _ctx(halted=True), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_secret_blocked_before_llm():
    with pytest.raises(pii.SecretsDetectedError):
        pii.apply_policy("use AKIAIOSFODNN7EXAMPLE now", policy="redact")


def test_redteam_pii_redacted_before_llm():
    out, findings = pii.apply_policy("ping me at red@team.com", policy="redact")
    assert "red@team.com" not in out and findings
```

- [ ] **Step 2: Run** (these reuse already-implemented modules from prior plans)

```bash
.venv/bin/python -m pytest tests/test_governance_redteam.py -v
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_governance_redteam.py
git commit -m "test(governance): red-team suite — every forbidden path blocked"
```

### Task 4: §5 deliverable documents

**Files:**
- Create: `docs/governance/audit_schema.md`, `docs/governance/governance_tests.md`, `scripts/rollbacks/README.md`

- [ ] **Step 1: `docs/governance/audit_schema.md`** — document the audit record the system writes (mirror `app/models/audit.py` + the hash chain):

```markdown
# Audit Record Schema (NDB Std §Audit Trail)

Every governed decision/action is written by `app/core/audit.py::record_action()`
to the append-only, hash-chained `audit_logs` table.

| Field | Type | Meaning |
|-------|------|---------|
| timestamp | datetime (UTC) | when recorded |
| agent_name | string | agent that acted |
| action | string | e.g. `gatekeeper:allow`, `EMERGENCY_HALT`, `pii_redaction` |
| action_category | string | observe/annotate/notify/contain_soft/contain_hard/remediate/mutate |
| confidence | string(float) | model confidence at decision |
| human_reviewer | string\|null | approver id/email when applicable |
| rollback_possible | bool\|null | whether a rollback was registered |
| risk_tier | string | critical/high/medium/low |
| input_hash / output_hash | sha256 | tamper-evident content hashes |
| request_id | uuid | correlation id |
| prev_hash / entry_hash | sha256 | hash chain (verify via `GET /audit/verify`) |

Integrity: deletion is forbidden (no delete endpoint; DB delete grant revoked in prod).
Tamper-evidence: `entry_hash = sha256(canonical(record) || prev_hash)`; `GET /audit/verify`
recomputes the chain and reports the first broken row, if any.
```

- [ ] **Step 2: `docs/governance/governance_tests.md`** — the red-team results narrative pointing at the suite:

```markdown
# Governance Test Results (Red Team)

Machine-checkable evidence: `tests/test_governance_redteam.py` (+ `test_gatekeeper.py`,
`test_pii.py`, `test_safety_envelope.py`). Run:

    .venv/bin/python -m pytest tests/test_governance_redteam.py -v

| Attack / forbidden path | Expected control | Test |
|-------------------------|------------------|------|
| `mutate` in POC | gatekeeper DENY | test_redteam_mutate_blocked_in_poc |
| action above autonomy tier | gatekeeper DENY | test_redteam_action_above_autonomy_blocked |
| contain/remediate w/o rollback | gatekeeper DENY | test_redteam_contain_without_rollback_blocked |
| low-confidence action | escalate to human | test_redteam_low_confidence_escalated |
| any action while halted | gatekeeper DENY | test_redteam_halt_blocks_everything |
| secret sent to LLM | blocked pre-call | test_redteam_secret_blocked_before_llm |
| PII sent to LLM | redacted pre-call | test_redteam_pii_redacted_before_llm |

Live metrics for the Success Criteria: `GET /api/v1/governance/metrics`.
```

- [ ] **Step 3: `scripts/rollbacks/README.md`** — rollback procedure conventions:

```markdown
# Rollback Procedures (NDB Std §Safety Envelope)

Rollbacks are **declarative**: each envelope tool (`contain_soft`/`contain_hard`/
`remediate`) declares a `rollback_command_template` (and optional
`validation_`/`verification_command_template`). On a successful action,
`execute_tool()` registers the computed rollback argv in `rollback_registrations`
with a TTL (default 3600s).

- Trigger a revert: `POST /api/v1/governance/rollback/{action_id}` (admin).
- List active registrations: `GET /api/v1/governance/rollback`.
- On rollback failure the on-call is paged (`rollback.failed` webhook event).

Add per-tool rollback scripts here when a single inverse command is insufficient,
and reference them from the tool's `rollback_command_template`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/governance/audit_schema.md docs/governance/governance_tests.md scripts/rollbacks/README.md
git commit -m "docs(governance): POC §5 deliverables — audit schema, red-team results, rollback procedures"
```

**Plan gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

## Self-Review notes (coverage vs the Standard §5)

- **Deliverables checklist:** `agent_governance.yaml` (governance-config export) · `src/gatekeeper.py` ⇒ `app/services/gatekeeper.py` · `src/kill_switch.py` ⇒ `app/services/kill_switch.py` · `docs/audit_schema.md` ⇒ Task 4 · `scripts/rollbacks/` ⇒ Task 4 · `test/governance_tests.md` ⇒ Task 4 + Task 3 suite. All §5 artifacts now exist (paths adapted to this repo's layout — note the mapping for the auditor).
- **Success Criteria:** all five metrics computed and exposed (Task 1–2), each with target + pass/fail and an `all_pass` roll-up.
- **Known limitations (call out at review):** `kill_switch_response_seconds` is a **synthetic probe** (engage→observe), not a production-traffic measurement — it validates the mechanism's latency, which is what the Standard's "<3s response" intends, but a true end-to-end SOC drill should be run separately for sign-off. `human_override_rate` approximates "override" as approval rejections (the system has no separate "human edited the AI's proposal" signal). Metrics are unweighted counts over the window; segmenting "of L2 actions" precisely requires tagging each approval with the agent's autonomy tier — a small enhancement (add `autonomy_tier` to the approval payload) if NDB wants the exact denominator.
- **Remaining after this plan:** `master.py` second-exec-path governance wiring (closes B2's last gap); audit WORM object-lock export (B4 phase-2). Both are small, independent follow-up plans.
