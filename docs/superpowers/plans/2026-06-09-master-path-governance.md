# Master-Agent Path Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the last B2/B3 coverage gap on the Master-Agent's task-dispatch path — stop dispatching new sub-agent tasks when the kill switch is engaged, and log every dispatch decision to the audit trail.

**Architecture:** A focused, **small** change. The heavy lifting is already done: internal sub-agents run their tools through the governed `execute_tool()` (gatekeeper + kill switch + audit), and `LocalAgentExecutor.execute()` is **LLM-only (runs no tools)**, so it cannot bypass the tool gatekeeper. The remaining gap is at the *orchestration* level — `master.py`'s `run_task()` can dispatch an LLM-only or remote task even while the system is halted, and these dispatches are not individually audited. This plan adds a halt gate and a dispatch-audit at that one function.

**Tech Stack:** Python/asyncio, the kill-switch + audit services from the earlier plans, pytest. No DB migration.

---

## Dependencies & scope

- **Depends on:** `app/services/kill_switch.py` (Phase-3 of `2026-06-09-agent-governance-controls.md`) and `app/core/audit.py::record_action()` (Phase-1).
- **Explicitly out of scope (already governed elsewhere):**
  - Internal sub-agents' tool calls → governed by `execute_tool()` (plans 1, 4).
  - LLM PII redaction on any path → governed by `LLMRouter._guard_messages()` (PII plan).
  - Remote/OpenClaw "black box" agents → the Standard says these must be *wrapped*; wrapping them is a separate effort, not this plan. This plan still **halts their dispatch**, which is the available lever.

## File Structure

| File | Responsibility |
|------|----------------|
| `app/agents/master.py` (modify) | Halt gate + dispatch audit inside `run_task()` |
| `tests/test_master_governance.py` (create) | Halt blocks dispatch; dispatch is audited |

---

### Task 1: Halt gate + dispatch audit in `run_task()`

**Files:**
- Modify: `app/agents/master.py`
- Test: `tests/test_master_governance.py`

- [ ] **Step 1: Write the failing test** (drive `run_task` indirectly via a tiny harness; mock the executors and the kill switch)

```python
# tests/test_master_governance.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_halted_master_refuses_to_dispatch(monkeypatch):
    """When the kill switch is engaged, run_task returns a halted result and
    does NOT call the local executor."""
    from app.agents.master import MasterAgent
    m = MasterAgent()

    local = AsyncMock()
    local.execute = AsyncMock(return_value={"status": "completed", "output": "x"})
    with patch.object(m, "_get_local_executor", return_value=local), \
         patch("app.services.kill_switch.is_halted", AsyncMock(return_value=True)), \
         patch("app.core.audit.record_action", AsyncMock()):
        run_task = m._build_run_task(user_id=1, state={"context": {}})   # see Step 3
        key, result = await run_task({"agent_type": "general", "task": "do thing"})

    assert result["status"] == "halted"
    local.execute.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_is_audited(monkeypatch):
    from app.agents.master import MasterAgent
    m = MasterAgent()
    local = AsyncMock()
    local.execute = AsyncMock(return_value={"status": "completed", "output": "x"})
    with patch.object(m, "_get_local_executor", return_value=local), \
         patch("app.services.kill_switch.is_halted", AsyncMock(return_value=False)), \
         patch("app.core.audit.record_action", AsyncMock()) as rec:
        run_task = m._build_run_task(user_id=1, state={"context": {}})
        await run_task({"agent_type": "general", "task": "do thing"})
    rec.assert_awaited()   # dispatch produced an audit record
```

- [ ] **Step 2: Run to verify failure**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_master_governance.py -v
```
Expected: FAIL — `MasterAgent has no attribute _build_run_task` (the closure isn't extracted yet).

- [ ] **Step 3: Extract `run_task` into a testable method + add the gate.** In `app/agents/master.py`, the existing `run_task` closure lives inside the dispatch node. Refactor it into a method `_build_run_task(self, user_id, state)` that returns the async `run_task` callable (preserving today's behaviour), and add the halt gate + audit at its top:

```python
    def _build_run_task(self, user_id, state):
        async def run_task(task):
            from app.services.kill_switch import is_halted
            from app.core.audit import record_action

            agent_type = task.get("agent_type", "general")
            task_desc = task.get("task", "")
            agent_id = task.get("agent_id")
            agent_name = task.get("agent_name")

            # Kill switch — do not dispatch new work while halted (NDB Std §Kill Switch).
            if await is_halted(agent_id=agent_id):
                await record_action(
                    user_id=user_id, agent_id=agent_id, agent_name=agent_name or agent_type,
                    action="dispatch:halted", action_category="annotate",
                    input_data={"task": task_desc[:500]}, output_data={"halted": True})
                return str(agent_id or agent_type), {"status": "halted",
                                                     "error": "kill switch engaged — dispatch refused"}

            # Audit the dispatch decision (NDB Std §Audit Trail — every decision logged).
            await record_action(
                user_id=user_id, agent_id=agent_id, agent_name=agent_name or agent_type,
                action="dispatch", action_category="annotate",
                input_data={"task": task_desc[:500], "agent_type": agent_type},
                output_data={"dispatched": True})

            # --- existing routing logic below, unchanged ---
            # (remote by id → by name → by backend type → local executor)
            ...
        return run_task
```

Then, at the original call site, replace the inline `async def run_task(...)` definition with:
```python
        run_task = self._build_run_task(user_id, state)
```

> Keep the body of the routing logic byte-for-byte as it is today; only the wrapper, the halt gate, and the two `record_action` calls are new.

- [ ] **Step 4: Run to verify pass**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_master_governance.py -v
```
Expected: both PASS.

- [ ] **Step 5: Run the master/agent suite for regressions**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q -k "master or agent or integration"
```
Expected: all pass (routing behaviour unchanged).

- [ ] **Step 6: Commit**

```bash
git add app/agents/master.py tests/test_master_governance.py
git commit -m "feat(governance): master-agent dispatch halt gate + audit (closes B2/B3 gap)"
```

---

## Self-Review notes

- **B3 at orchestration level** → halt now stops new task dispatch, covering LLM-only/remote tasks that never reach `execute_tool()`.
- **B4 completeness** → every dispatch decision is audited (`dispatch` / `dispatch:halted`).
- **Honest scope:** this is deliberately small because the sub-agent tool path was already governed. The only thing this plan does NOT solve is true *wrapping* of remote/OpenClaw "black box" agents (so their internal tool calls are gatekept) — that is a larger, separate effort the Standard calls out ("Third-party black box agents must be wrapped"). Dispatch-level halt is the available control until wrapping is built.
