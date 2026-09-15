# Model-Authored Code Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agent write a Python script mid-conversation and run it in the existing sandbox, gated by a per-agent execution mode.

**Architecture:** `run_python` is a built-in tool in `InternalAgentRunner`, never a `Tool` row. In `approval` mode its first call creates an approval record pinning `sha256(code)` and returns `needs_approval`, which the **existing** `validation_node → approval_node → re_execute` loop turns into a graph suspension and resume. Execution reuses `skill-runner` with a one-file bundle and no network.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, LangGraph, pytest, React/TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-15-chat-code-execution-design.md`

## Global Constraints

- **Never raise `interrupt()` from the tool loop.** `master.py:687` uses `asyncio.gather(..., return_exceptions=True)`, which swallows `GraphInterrupt` into a "failed sub-agent" result. Suspension happens only in `approval_node`.
- Execution requires an **approved record whose `code_digest` matches the code being run**, scoped to `(request_id, digest)`. No digest match, no execution.
- `run_python` always runs with `script_network = "none"`. Phase 2's allowlist is not available to it.
- The approval requirement in `approval` mode is **in code, not gatekeeper policy** — it must not read a threshold that can be relaxed to zero.
- `_tool_meta("run_python")` returns `action_category="mutate"`, `risk_tier="high"` — never `observe`/`low` like the other built-ins.
- Cap: **3** `run_python` approval rounds per `request_id`.
- `AUTO_APPROVE` is not modified. `code_execution_mode` is the production control.
- New migration: `039_agent_code_execution_mode`, `down_revision = "038_skill_script_tools"`.
- Run the suite with `make test`. One file: `make test-env-up`, then `DATABASE_URL=postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test REDIS_URL=redis://:cyberguard-test-only@localhost:56379/0 REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(python3 -c "print('0'*64)") SECRET_KEY=$(python3 -c "print('1'*64)") ENVIRONMENT=testing AUTO_APPROVE=false .venv/bin/python -m pytest <file> -v`.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/services/code_approval.py` (create) | Digest of code; find/create the approval record for `(request_id, digest)`; round counting |
| `app/models/agent.py` (modify) | `code_execution_mode` column |
| `alembic/versions/039_agent_code_execution_mode.py` (create) | The migration |
| `app/services/internal_agent.py` (modify) | `run_python` tool schema, dispatch branch, `_tool_meta` entry, accept `request_id` + mode |
| `app/services/agent_executor.py` (modify) | Forward `request_id` and `code_execution_mode` from `context` into the runner |
| `app/services/code_runner.py` (create) | Send one-file code to `skill-runner`; the only thing that knows the sandbox wire format for this feature |
| `app/routers/agents.py` (modify) | Validate the mode on write, audit the change |
| `webui/src/pages/Approvals.tsx` (modify) | Render proposed code as code, not as JSON |

---

### Task 1: Code digest and approval lookup

**Files:**
- Create: `app/services/code_approval.py`
- Test: `tests/test_code_approval.py`

**Interfaces:**
- Produces:
  - `code_digest(code: str) -> str` — 64-char lowercase hex
  - `CODE_APPROVAL_ACTION_TYPE = "code.execute"`
  - `MAX_CODE_APPROVAL_ROUNDS = 3`
  - `async find_approved(db, request_id: str, digest: str) -> Optional[ApprovalRequest]`
  - `async count_rounds(db, request_id: str) -> int`
  - `async create_pending(db, *, request_id: str, digest: str, code: str, user_id: int, agent_id, agent_name) -> ApprovalRequest`

- [ ] **Step 1: Write the failing test**

Create `tests/test_code_approval.py`:

```python
"""Approval binds to one specific piece of code, in one specific run."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.code_approval import (
    CODE_APPROVAL_ACTION_TYPE,
    MAX_CODE_APPROVAL_ROUNDS,
    code_digest,
)


def test_digest_is_stable_and_hex():
    d = code_digest("print(1)")
    assert d == code_digest("print(1)")
    assert len(d) == 64 and d == d.lower()


def test_digest_changes_with_any_edit():
    assert code_digest("print(1)") != code_digest("print(2)")
    assert code_digest("print(1)") != code_digest("print(1) ")


def test_digest_is_not_normalized_away():
    # Whitespace is semantic in Python, so it must be part of the identity.
    assert code_digest("if x:\n  a()") != code_digest("if x:\n    a()")


def test_action_type_is_distinct_from_tool_execute():
    # tool.execute records are the ones graph_resume_target refuses to resume.
    # Using a distinct type keeps the two populations separable in the audit.
    assert CODE_APPROVAL_ACTION_TYPE == "code.execute"


def test_round_cap_is_three():
    assert MAX_CODE_APPROVAL_ROUNDS == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_approval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.code_approval'`

- [ ] **Step 3: Write minimal implementation**

Create `app/services/code_approval.py`:

```python
"""Approval records for model-authored code.

The digest is what makes an approval mean something here. The graph re-runs
its executor node on resume, so the model is called again and may author
different code; without pinning the digest, an approval granted for reviewed
code would cover whatever the model produced the second time.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Deliberately not "tool.execute": those are the records graph_resume_target
# refuses to resume, and keeping the populations separate keeps the audit
# readable.
CODE_APPROVAL_ACTION_TYPE = "code.execute"
MAX_CODE_APPROVAL_ROUNDS = 3


def code_digest(code: str) -> str:
    """sha256 of the exact bytes that would run. No normalization."""
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


async def find_approved(db: AsyncSession, request_id: str, digest: str):
    """An approved record authorizing exactly this code in exactly this run."""
    from app.models.approval import ApprovalRequest

    rows = (
        await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE,
                ApprovalRequest.status == "approved",
            )
        )
    ).scalars().all()
    for row in rows:
        payload = row.payload or {}
        if payload.get("run_request_id") == request_id and \
                payload.get("code_digest") == digest:
            return row
    return None


async def count_rounds(db: AsyncSession, request_id: str) -> int:
    """How many code approvals this run has already opened."""
    from app.models.approval import ApprovalRequest

    rows = (
        await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE
            )
        )
    ).scalars().all()
    return sum(1 for r in rows if (r.payload or {}).get("run_request_id") == request_id)


async def create_pending(
    db: AsyncSession, *, request_id: str, digest: str, code: str,
    user_id: int, agent_id: Optional[int], agent_name: Optional[str],
):
    """Open an approval carrying the full code, so a human reviews what runs."""
    import uuid

    from app.services.approval_service import ApprovalService

    return await ApprovalService.create_request(
        request_id=str(uuid.uuid4()),
        user_id=user_id,
        action_type=CODE_APPROVAL_ACTION_TYPE,
        action_description=(
            f"Agent {agent_name!r} proposes running {len(code)} characters of Python"
        ),
        agent_id=agent_id,
        agent_name=agent_name,
        payload={
            "run_request_id": request_id,
            "code_digest": digest,
            "code": code,
            "approval_type": "separation_of_duties",
        },
        risk_level="high",
        urgency="urgent",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_code_approval.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/code_approval.py tests/test_code_approval.py
git commit -m "feat: add code approval records keyed by digest"
```

---

### Task 2: Per-agent execution mode column

**Files:**
- Modify: `app/models/agent.py`
- Create: `alembic/versions/039_agent_code_execution_mode.py`
- Test: `tests/test_code_execution_mode.py`

**Interfaces:**
- Produces: `AgentConfig.code_execution_mode`, values `off` | `approval` | `auto`, default `approval`

- [ ] **Step 1: Write the failing test**

Create `tests/test_code_execution_mode.py`:

```python
"""The per-agent switch for model-authored code execution."""
from __future__ import annotations

from app.models.agent import AgentConfig


def test_agent_config_has_the_mode_column():
    assert "code_execution_mode" in AgentConfig.__table__.columns


def test_mode_defaults_to_approval_so_nothing_opens_silently():
    col = AgentConfig.__table__.columns["code_execution_mode"]
    assert col.default.arg == "approval"
    assert col.server_default.arg == "approval"
    assert col.nullable is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_execution_mode.py -v`
Expected: FAIL — `KeyError: 'code_execution_mode'`

- [ ] **Step 3: Write minimal implementation**

In `app/models/agent.py`, inside `class AgentConfig`, after `escalate_to_human_below`:

```python
    # off | approval | auto. Default `approval`: an existing agent gains the
    # capability in its gated form and nothing opens without someone saying so.
    code_execution_mode = Column(
        String(20), nullable=False, server_default="approval", default="approval"
    )
```

Create `alembic/versions/039_agent_code_execution_mode.py`:

```python
"""Per-agent mode for model-authored code execution.

Revision ID: 039_agent_code_execution_mode
Revises: 038_skill_script_tools
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "039_agent_code_execution_mode"
down_revision: Union[str, None] = "038_skill_script_tools"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("code_execution_mode", sa.String(length=20),
                  nullable=False, server_default="approval"),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "code_execution_mode")
```

- [ ] **Step 4: Run the test and apply the migration**

Run: `.venv/bin/python -m pytest tests/test_code_execution_mode.py -v`
Expected: 2 passed

Run: `make test-env-up && DATABASE_URL=postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test REDIS_URL=redis://:cyberguard-test-only@localhost:56379/0 REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(python3 -c "print('0'*64)") SECRET_KEY=$(python3 -c "print('1'*64)") ENVIRONMENT=testing .venv/bin/python -m alembic upgrade head`
Expected: `Running upgrade 038_skill_script_tools -> 039_agent_code_execution_mode`

- [ ] **Step 5: Commit**

```bash
git add app/models/agent.py alembic/versions/039_agent_code_execution_mode.py tests/test_code_execution_mode.py
git commit -m "feat: add per-agent code execution mode"
```

---

### Task 3: Sandbox call for a one-file program

**Files:**
- Create: `app/services/code_runner.py`
- Test: `tests/test_code_runner.py`

**Interfaces:**
- Consumes: `app.services.tool_executor._post_to_runner`, `SKILL_RUNNER_URL`
- Produces: `async run_code(code: str, timeout: int = 30) -> Dict[str, Any]` — same result shape as a skill-script run

- [ ] **Step 1: Write the failing test**

Create `tests/test_code_runner.py`:

```python
"""Model-authored code goes to the no-network sandbox as a one-file bundle."""
from __future__ import annotations

import base64

import pytest

import app.services.code_runner as cr


@pytest.fixture(autouse=True)
def _capture(monkeypatch):
    calls = []

    async def fake_post(base_url, payload, timeout):
        calls.append({"url": base_url, "payload": payload, "timeout": timeout})
        return {"status": "completed", "stdout": "42", "exit_code": 0, "is_error": False}

    monkeypatch.setattr(cr, "_post_to_runner", fake_post)
    monkeypatch.setattr(cr, "SKILL_RUNNER_URL", "http://skill-runner:9000")
    monkeypatch.setattr(cr, "SKILL_RUNNER_NET_URL", "http://skill-runner-net:9000")
    cr._TEST_CALLS = calls
    return calls


@pytest.mark.asyncio
async def test_code_is_sent_as_a_single_main_py(_capture):
    result = await cr.run_code("print(6*7)", timeout=20)
    assert result["stdout"] == "42"

    call = _capture[-1]
    assert call["payload"]["argv"] == ["python3", "main.py"]
    files = call["payload"]["files"]
    assert len(files) == 1
    assert files[0]["path"] == "main.py"
    assert base64.b64decode(files[0]["content_b64"]).decode() == "print(6*7)"


@pytest.mark.asyncio
async def test_it_never_reaches_the_networked_runner(_capture):
    await cr.run_code("print(1)")
    assert _capture[-1]["url"] == "http://skill-runner:9000"


@pytest.mark.asyncio
async def test_no_proxy_url_is_ever_sent(_capture):
    # Phase 2's allowlist is not available to model-authored code.
    await cr.run_code("print(1)")
    assert "proxy_url" not in _capture[-1]["payload"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.code_runner'`

- [ ] **Step 3: Write minimal implementation**

Create `app/services/code_runner.py`:

```python
"""Run model-authored code in the no-network sandbox.

The sandbox already takes ``files`` plus ``argv``, so a model-authored program
is just a bundle with one file in it — no runner change was needed for this.

Deliberately imports SKILL_RUNNER_URL and never SKILL_RUNNER_NET_URL: code that
nobody wrote down in advance does not get egress.
"""
from __future__ import annotations

import base64
from typing import Any, Dict

from app.services.tool_executor import (  # noqa: F401 - re-exported for tests
    SKILL_RUNNER_NET_URL,
    SKILL_RUNNER_URL,
    _post_to_runner,
)

ENTRYPOINT = "main.py"
DEFAULT_TIMEOUT_SECONDS = 30


async def run_code(code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """Execute *code* as main.py in the sandbox. No network, no secrets."""
    payload = {
        "argv": ["python3", ENTRYPOINT],
        "timeout": int(timeout),
        "files": [{
            "path": ENTRYPOINT,
            "content_b64": base64.b64encode((code or "").encode("utf-8")).decode(),
        }],
    }
    return await _post_to_runner(SKILL_RUNNER_URL, payload, int(timeout))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_code_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/code_runner.py tests/test_code_runner.py
git commit -m "feat: run model-authored code as a one-file sandbox bundle"
```

---

### Task 4: Wire `request_id` and the mode into the runner

**Files:**
- Modify: `app/services/agent_executor.py:375-377`, `app/services/internal_agent.py:729-733`
- Test: `tests/test_code_execution_plumbing.py`

**Interfaces:**
- Produces: `InternalAgentRunner.execute(task, conversation_id, user_id, *, run_request_id=None)`; the runner reads `code_execution_mode` from its own config dict

- [ ] **Step 1: Write the failing test**

Create `tests/test_code_execution_plumbing.py`:

```python
"""run_python needs a run id to scope an approval by; today none arrives."""
from __future__ import annotations

import inspect

from app.services.internal_agent import InternalAgentRunner


def test_execute_accepts_a_run_request_id():
    sig = inspect.signature(InternalAgentRunner.execute)
    assert "run_request_id" in sig.parameters


def test_runner_reads_the_agent_code_execution_mode():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "a", "system_prompt": "p",
        "code_execution_mode": "auto", "metadata_json": {},
    })
    assert runner.code_execution_mode == "auto"


def test_mode_defaults_to_approval_when_the_config_omits_it():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "a", "system_prompt": "p", "metadata_json": {},
    })
    assert runner.code_execution_mode == "approval"


def test_executor_forwards_the_run_request_id():
    src = inspect.getsource(
        __import__("app.services.agent_executor", fromlist=["x"]))
    assert 'context or {}).get("request_id")' in src
    assert "run_request_id=" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_execution_plumbing.py -v`
Expected: FAIL — `assert 'run_request_id' in sig.parameters`

- [ ] **Step 3: Write minimal implementation**

In `app/services/internal_agent.py`, in `__init__` next to the other config reads (around line 129):

```python
        # off | approval | auto. Absent config means the gated default, never
        # the open one.
        self.code_execution_mode: str = (
            config.get("code_execution_mode") or "approval"
        )
```

Change the `execute` signature (line 729):

```python
    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int, *, run_request_id: Optional[str] = None) -> Dict[str, Any]:
```

and immediately after `self._user_id = user_id`:

```python
        # Scopes a code approval to this graph run. Without it run_python has no
        # key to ask "was this exact code approved for this run?".
        self._run_request_id = run_request_id
```

In `app/services/agent_executor.py`, replace lines 375-377:

```python
        if kind == "internal":
            runner = InternalAgentRunner(config_dict, pre_approved=pre_approved)
            conv_id = (context or {}).get("conversation_id")
            result = await runner.execute(task=task, conversation_id=conv_id, user_id=user_id)
```

with:

```python
        if kind == "internal":
            runner = InternalAgentRunner(config_dict, pre_approved=pre_approved)
            conv_id = (context or {}).get("conversation_id")
            run_request_id = (context or {}).get("request_id")
            result = await runner.execute(
                task=task, conversation_id=conv_id, user_id=user_id,
                run_request_id=run_request_id,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_code_execution_plumbing.py tests/test_internal_agent.py -v`
Expected: 4 passed plus the existing internal-agent tests

- [ ] **Step 5: Commit**

```bash
git add app/services/internal_agent.py app/services/agent_executor.py tests/test_code_execution_plumbing.py
git commit -m "feat: carry the run id and code execution mode into the runner"
```

---

### Task 5: The `run_python` tool

**Files:**
- Modify: `app/services/internal_agent.py` (`_build_tools`, `_tool_meta`, `_dispatch`)
- Test: `tests/test_run_python_tool.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4
- Produces: `InternalAgentRunner._run_python(code: str) -> Dict[str, Any]`; tool name `run_python` with one required string parameter `code`

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_python_tool.py`:

```python
"""run_python: mode routing, digest binding, and the round cap."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.internal_agent import InternalAgentRunner


def _runner(mode="approval", run_id="run-1"):
    r = InternalAgentRunner({
        "id": 7, "agent_name": "analyst", "system_prompt": "p",
        "code_execution_mode": mode, "metadata_json": {},
    })
    r._user_id = 3
    r._run_request_id = run_id
    return r


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    state = {"ran": [], "created": [], "approved": None, "rounds": 0}

    async def fake_run_code(code, timeout=30):
        state["ran"].append(code)
        return {"status": "completed", "stdout": "ok", "is_error": False}

    async def fake_find_approved(_db, request_id, digest):
        want = state["approved"]
        return SimpleNamespace(id=1) if want == (request_id, digest) else None

    async def fake_count_rounds(_db, _request_id):
        return state["rounds"]

    async def fake_create_pending(_db, **kw):
        state["created"].append(kw)
        return SimpleNamespace(id=99)

    import app.services.code_approval as ca
    import app.services.code_runner as cr
    monkeypatch.setattr(cr, "run_code", fake_run_code)
    monkeypatch.setattr(ca, "find_approved", fake_find_approved)
    monkeypatch.setattr(ca, "count_rounds", fake_count_rounds)
    monkeypatch.setattr(ca, "create_pending", fake_create_pending)

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.core.database.get_db_context", lambda: _DB())
    return state


@pytest.mark.asyncio
async def test_off_mode_refuses_without_creating_anything(_stubs):
    result = await _runner(mode="off")._run_python("print(1)")
    assert result["status"] == "error"
    assert _stubs["ran"] == [] and _stubs["created"] == []


@pytest.mark.asyncio
async def test_auto_mode_runs_without_an_approval_record(_stubs):
    result = await _runner(mode="auto")._run_python("print(1)")
    assert result["status"] == "completed"
    assert _stubs["ran"] == ["print(1)"]
    assert _stubs["created"] == []


@pytest.mark.asyncio
async def test_approval_mode_first_call_asks_and_does_not_run(_stubs):
    result = await _runner()._run_python("print(1)")
    assert result["status"] == "needs_approval"
    assert _stubs["ran"] == []
    assert len(_stubs["created"]) == 1
    assert _stubs["created"][0]["code"] == "print(1)"


@pytest.mark.asyncio
async def test_approval_mode_runs_once_that_exact_code_is_approved(_stubs):
    from app.services.code_approval import code_digest
    _stubs["approved"] = ("run-1", code_digest("print(1)"))
    result = await _runner()._run_python("print(1)")
    assert result["status"] == "completed"
    assert _stubs["ran"] == ["print(1)"]


@pytest.mark.asyncio
async def test_an_approval_for_other_code_does_not_authorize_this_code(_stubs):
    from app.services.code_approval import code_digest
    _stubs["approved"] = ("run-1", code_digest("print(1)"))
    result = await _runner()._run_python("import os; os.system('curl evil')")
    assert result["status"] == "needs_approval"
    assert _stubs["ran"] == []


@pytest.mark.asyncio
async def test_an_approval_from_another_run_does_not_carry_over(_stubs):
    from app.services.code_approval import code_digest
    _stubs["approved"] = ("run-OTHER", code_digest("print(1)"))
    result = await _runner(run_id="run-1")._run_python("print(1)")
    assert result["status"] == "needs_approval"
    assert _stubs["ran"] == []


@pytest.mark.asyncio
async def test_the_round_cap_refuses_rather_than_looping(_stubs):
    _stubs["rounds"] = 3
    result = await _runner()._run_python("print(1)")
    assert result["status"] == "error"
    assert "approval" in result["error"].lower()
    assert _stubs["created"] == []


def test_the_tool_is_not_classified_as_a_read_only_builtin():
    meta = _runner()._tool_meta("run_python")
    assert meta["action_category"] == "mutate"
    assert meta["risk_tier"] == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_run_python_tool.py -v`
Expected: FAIL — `AttributeError: 'InternalAgentRunner' object has no attribute '_run_python'`

- [ ] **Step 3: Write minimal implementation**

In `app/services/internal_agent.py`, add the method next to `_request_approval`:

```python
    async def _run_python(self, code: str) -> Dict[str, Any]:
        """Execute model-authored code, gated by this agent's execution mode.

        In `approval` mode the gate is here in code rather than in gatekeeper
        policy: removing the human is meant to be an explicit, audited change of
        `code_execution_mode`, not a threshold someone lowers to zero.
        """
        from app.core.database import get_db_context
        from app.services import code_approval, code_runner

        mode = getattr(self, "code_execution_mode", "approval")
        if mode == "off":
            return {"status": "error", "is_error": True,
                    "error": "this agent is not permitted to execute code"}

        if mode == "auto":
            return await code_runner.run_code(code)

        run_id = getattr(self, "_run_request_id", None)
        if not run_id:
            return {"status": "error", "is_error": True,
                    "error": "no run id available to scope a code approval"}

        digest = code_approval.code_digest(code)
        async with get_db_context() as db:
            if await code_approval.find_approved(db, run_id, digest):
                return await code_runner.run_code(code)

            if await code_approval.count_rounds(db, run_id) >= \
                    code_approval.MAX_CODE_APPROVAL_ROUNDS:
                return {
                    "status": "error", "is_error": True,
                    "error": (
                        "too many code approval rounds in this run; the proposed "
                        "code kept changing between approvals"
                    ),
                }

            await code_approval.create_pending(
                db, request_id=run_id, digest=digest, code=code,
                user_id=getattr(self, "_user_id", 0) or 0,
                agent_id=self.agent_id, agent_name=self.agent_name,
            )

        return {
            "status": "needs_approval", "is_error": True,
            "error": ("this code needs human approval before it can run; "
                      "propose the identical code again after it is approved"),
        }
```

In `_tool_meta`, before the existing built-in branch:

```python
        if name == "run_python":
            # The one built-in that executes caller-authored code. Grouping it
            # with the read-only helpers would hide it from category rules.
            return {"action_category": "mutate", "risk_tier": "high",
                    "transport": "builtin"}
```

In `_build_tools`, before the `knowledge_base_id` block:

```python
        if getattr(self, "code_execution_mode", "approval") != "off":
            tools.append({
                "type": "function",
                "function": {
                    "name": "run_python",
                    "description": (
                        "Run a short Python program in an isolated sandbox with no "
                        "network access and the standard library only. Use it to "
                        "compute, parse or transform data you already have. Unless "
                        "this agent is in auto mode the code is shown to a human "
                        "for approval before it runs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string",
                                     "description": "The complete Python program."},
                        },
                        "required": ["code"],
                    },
                },
            })
```

In `_dispatch`'s `_execute`, add a branch after the `load_skill` branch:

```python
            # 1c. Model-authored code
            if name == "run_python":
                res = await self._run_python(bound_args.get("code") or "")
                if res.get("status") == "completed":
                    return res.get("stdout", "") or "(no output)"
                return res
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_run_python_tool.py tests/test_internal_agent.py tests/test_skill_progressive.py -v`
Expected: 8 passed plus the existing suites

- [ ] **Step 5: Commit**

```bash
git add app/services/internal_agent.py tests/test_run_python_tool.py
git commit -m "feat: add the run_python built-in tool"
```

---

### Task 6: Mode validation on write, and the approval UI

**Files:**
- Modify: `app/routers/agents.py`, `webui/src/pages/Approvals.tsx`, `webui/src/i18n/en.json`, `webui/src/i18n/zh.json`
- Test: `tests/test_code_execution_mode.py`

**Interfaces:**
- Produces: `app.routers.agents.CODE_EXECUTION_MODES`; `validate_code_execution_mode(value) -> str`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_code_execution_mode.py`:

```python
import pytest
from fastapi import HTTPException

from app.routers.agents import CODE_EXECUTION_MODES, validate_code_execution_mode


def test_the_three_modes_are_the_only_ones_accepted():
    assert CODE_EXECUTION_MODES == ("off", "approval", "auto")
    for mode in CODE_EXECUTION_MODES:
        assert validate_code_execution_mode(mode) == mode


def test_an_unknown_mode_is_refused():
    with pytest.raises(HTTPException, match="code_execution_mode"):
        validate_code_execution_mode("yolo")


def test_none_means_leave_it_alone():
    assert validate_code_execution_mode(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_code_execution_mode.py -v`
Expected: FAIL — `ImportError: cannot import name 'CODE_EXECUTION_MODES'`

- [ ] **Step 3: Write minimal implementation**

In `app/routers/agents.py`, near the top-level constants:

```python
CODE_EXECUTION_MODES = ("off", "approval", "auto")


def validate_code_execution_mode(value):
    """Reject unknown modes at the edge; `None` leaves the stored value alone."""
    if value is None:
        return None
    if value not in CODE_EXECUTION_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"code_execution_mode must be one of {', '.join(CODE_EXECUTION_MODES)}",
        )
    return value
```

In `update_agent` (the `PUT /agents/{agent_id}` handler), after the agent row is
loaded and before its fields are updated from the body, call it and audit a change:

```python
    incoming_mode = validate_code_execution_mode(
        body.model_dump(exclude_unset=True).get("code_execution_mode"))
    if incoming_mode is not None and incoming_mode != agent.code_execution_mode:
        from app.core.audit import record_action
        await record_action(
            user_id=current_user.user_id, action="agent.code_execution_mode",
            agent_id=agent.id, agent_name=agent.agent_name,
            risk_tier="high" if incoming_mode == "auto" else "medium",
            human_reviewer=str(current_user.user_id),
            input_data={"from": agent.code_execution_mode, "to": incoming_mode},
            output_data={"changed": True},
        )
```

Add `code_execution_mode: Optional[str] = None` to the agent create and update schemas in `app/schemas/agent.py`, and include it in the agent read schema.

In `webui/src/i18n/en.json` under `approvals`:

```json
    "proposedCode": "Proposed code",
    "proposedCodeHint": "This program will run in an isolated sandbox with no network access."
```

In `webui/src/i18n/zh.json` under `approvals`:

```json
    "proposedCode": "待执行代码",
    "proposedCodeHint": "该程序将在无网络访问的隔离沙箱中运行。"
```

In `webui/src/pages/Approvals.tsx`, before the generic payload block that renders
`JSON.stringify(item.payload, null, 2)`, add a dedicated renderer so a reviewer
reads code as code rather than as an escaped JSON string:

```tsx
                    {typeof item.payload?.code === 'string' && (
                      <div style={{ marginBottom: 10 }}>
                        <div style={{ fontSize: 11, color: 'var(--accent)', letterSpacing: '0.1em', marginBottom: 4 }}>
                          {t('approvals.proposedCode').toUpperCase()}
                        </div>
                        <pre style={{
                          margin: 0, padding: 10, maxHeight: 320, overflow: 'auto',
                          background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                          fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                        }}>{item.payload.code as string}</pre>
                        <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                          {t('approvals.proposedCodeHint')}
                        </div>
                      </div>
                    )}
```

- [ ] **Step 4: Run every gate**

Run: `.venv/bin/python -m pytest tests/test_code_execution_mode.py -v`
Expected: 5 passed

Run: `make check`
Expected: Python suite green, tsc app + test, eslint at baseline, npm audit clean, vitest passing

- [ ] **Step 5: Commit**

```bash
git add app/routers/agents.py app/schemas/agent.py webui/src/pages/Approvals.tsx \
        webui/src/i18n/en.json webui/src/i18n/zh.json tests/test_code_execution_mode.py
git commit -m "feat: validate the execution mode and show proposed code for review"
```

---

### Task 7: End-to-end and documentation

**Files:**
- Create: `tests/test_chat_code_execution_e2e.py`
- Modify: `docs/delivery/ARCHITECTURE_AND_SECURITY.md`
- Test: `tests/test_invariants_static.py`

- [ ] **Step 1: Write the end-to-end and invariant tests**

Create `tests/test_chat_code_execution_e2e.py`:

```python
"""Propose, approve, run — and a changed proposal does not inherit the approval."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.database import get_db_context
from app.models.approval import ApprovalRequest
from app.services.code_approval import (
    CODE_APPROVAL_ACTION_TYPE, code_digest, count_rounds, create_pending, find_approved,
)

RUN_ID = "e2e-code-run"


async def _cleanup(db):
    rows = (await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE))).scalars().all()
    for r in rows:
        if (r.payload or {}).get("run_request_id") == RUN_ID:
            await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id == r.id))
    await db.commit()


@pytest.mark.asyncio
async def test_approval_binds_to_the_code_and_the_run():
    code = "print(6*7)"
    digest = code_digest(code)

    async with get_db_context() as db:
        await _cleanup(db)
        try:
            record = await create_pending(
                db, request_id=RUN_ID, digest=digest, code=code,
                user_id=1, agent_id=None, agent_name="analyst")

            # Pending authorizes nothing.
            assert await find_approved(db, RUN_ID, digest) is None

            row = (await db.execute(select(ApprovalRequest).where(
                ApprovalRequest.id == record.id))).scalar_one()
            row.status = "approved"
            await db.commit()

            assert await find_approved(db, RUN_ID, digest) is not None
            # A different program, and the same program in a different run.
            assert await find_approved(db, RUN_ID, code_digest("print(1)")) is None
            assert await find_approved(db, "other-run", digest) is None
            assert await count_rounds(db, RUN_ID) == 1
        finally:
            await _cleanup(db)
```

Create `tests/test_code_needs_approval_routes.py`:

```python
"""The linchpin: run_python's needs_approval must reach the approval node.

D1 rests entirely on master.py picking up a needs_approval sub-result. If that
wiring ever changes, run_python would silently return "needs approval" to the
model and the graph would summarise instead of suspending — no approval, no
execution, no error.
"""
from __future__ import annotations

from app.agents.master import MasterAgent


def test_a_needs_approval_sub_result_routes_to_the_approval_node():
    state = {"approval_required": True, "approval_status": None}
    assert MasterAgent._validation_decision(MasterAgent, state) == "rejected"


def test_a_spent_approval_does_not_satisfy_the_next_gate():
    # approval_granted_round must equal the current round, or the first
    # approval in a thread would stand in for every later one.
    state = {
        "approval_required": True, "approval_status": "approved",
        "approval_granted_round": 0, "approval_round": 1,
    }
    assert MasterAgent._validation_decision(MasterAgent, state) == "rejected"


def test_a_current_approval_lets_the_run_continue():
    state = {
        "approval_required": True, "approval_status": "approved",
        "approval_granted_round": 1, "approval_round": 1,
    }
    assert MasterAgent._validation_decision(MasterAgent, state) == "approved"
```

Append to `tests/test_invariants_static.py`:

```python
# --------------------------------------------------------------------------
# INV-42 · model-authored code never gets egress
# --------------------------------------------------------------------------

def test_inv42_code_runner_never_uses_the_networked_runner():
    """INV-42: run_python goes to the no-network sandbox, always.

    Phase 2's allowlist exists for scripts a human reviewed and named hosts
    for. Code written seconds ago by a model has neither.
    """
    source = (REPO / "app" / "services" / "code_runner.py").read_text()
    body = source.split("async def run_code", 1)[1]
    assert "SKILL_RUNNER_NET_URL" not in body
    assert "proxy_url" not in body
    assert "SKILL_RUNNER_URL" in body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_code_needs_approval_routes.py -v`
Expected: PASS — this asserts existing behavior that D1 depends on. If it fails,
stop: the routing the whole design rests on is not what the spec claims.

Run: `.venv/bin/python -m pytest tests/test_invariants_static.py -k inv42 -v`
Expected: PASS — it guards the file Task 3 already created. If it fails, Task 3
reached for the networked runner and must be fixed before going further.

- [ ] **Step 3: Update the documentation**

Append to the "Executable skill scripts" section of `docs/delivery/ARCHITECTURE_AND_SECURITY.md`:

```markdown
### Model-authored code in chat

An agent can also write a Python program during a conversation and run it, via
the `run_python` built-in. This is a different trust object from a promoted
skill script: nobody reviewed it in advance, so it carries none of the
promotion machinery and none of the egress.

Each agent has a `code_execution_mode`: `off`, `approval` (the default) or
`auto`. In `approval` mode the first call opens an approval carrying the full
program and its sha256, and the graph suspends at its existing approval node —
the only node with no side effects, which is why suspension is safe there. The
program runs only when an approved record matches both the run and the exact
digest, so an approval cannot be reused for code the model rewrote on resume.

`auto` skips the human and nothing else: the kill switch, the gatekeeper, the
audit chain, the sandbox and the network isolation all still apply, and every
auto execution is audited with the program and its digest. `AUTO_APPROVE`
remains a development-only convenience; `code_execution_mode` is the production
control, changed per agent under `AGENT_WRITE` and recorded in the audit trail.

Model-authored code always runs in the no-network sandbox (INV-42). See
`docs/superpowers/specs/2026-09-15-chat-code-execution-design.md`.
```

- [ ] **Step 4: Run every gate**

Run: `make check`
Expected: all green

Run: `make test-env-up && DATABASE_URL=postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test REDIS_URL=redis://:cyberguard-test-only@localhost:56379/0 REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(python3 -c "print('0'*64)") SECRET_KEY=$(python3 -c "print('1'*64)") ENVIRONMENT=testing AUTO_APPROVE=false .venv/bin/python -m pytest tests/test_chat_code_execution_e2e.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_chat_code_execution_e2e.py tests/test_code_needs_approval_routes.py \
        tests/test_invariants_static.py docs/delivery/ARCHITECTURE_AND_SECURITY.md
git commit -m "test: end-to-end code approval binding, and INV-42"
```

---

## Deferred

The stronger design in spec §3.1 — the executor node running approved-but-unexecuted code records directly, so the model never has to reproduce its own program — is not built here. Neither is the pre-existing replay behavior in spec §9, where `re_execute` re-runs the whole executor node and repeats sibling sub-agents' already-executed tools. Both would be addressed by making that node resumable rather than replayable, which is its own piece of work.
