"""Propose, approve, run — through _run_python against a real database."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.database import get_db_context
from app.models.approval import ApprovalRequest
from app.services.code_approval import CODE_APPROVAL_ACTION_TYPE, code_digest
from app.services.internal_agent import InternalAgentRunner

RUN = "e2e-code-run"
CODE = "print(6*7)"


def _runner(mode="approval"):
    r = InternalAgentRunner({
        "id": None, "agent_name": "e2e-analyst", "system_prompt": "p",
        "code_execution_mode": mode, "metadata_json": {},
    })
    r._user_id = 1
    r._run_request_id = RUN
    return r


async def _cleanup(db):
    rows = (await db.execute(select(ApprovalRequest).where(
        ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE))).scalars().all()
    for r in rows:
        if (r.payload or {}).get("run_request_id") == RUN:
            await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id == r.id))
    await db.commit()


@pytest.fixture
def sandbox(monkeypatch):
    """Stand in for the sandbox; this test is about the approval path."""
    ran = []

    async def fake_run_code(code, timeout=30):
        ran.append(code)
        return {"status": "completed", "stdout": "42", "is_error": False}

    import app.services.code_runner as cr
    monkeypatch.setattr(cr, "run_code", fake_run_code)
    return ran


@pytest.mark.asyncio
async def test_propose_then_approve_then_run(sandbox):
    async with get_db_context() as db:
        await _cleanup(db)
    try:
        # 1. First call proposes and refuses to run.
        first = await _runner()._run_python(CODE)
        assert first["status"] == "needs_approval"
        assert sandbox == []

        async with get_db_context() as db:
            row = (await db.execute(select(ApprovalRequest).where(
                ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE,
            ))).scalars().all()
            mine = [r for r in row if (r.payload or {}).get("run_request_id") == RUN]
            assert len(mine) == 1
            # The reviewer sees the program itself, not a reference to it.
            assert mine[0].payload["code"] == CODE
            assert mine[0].payload["code_digest"] == code_digest(CODE)

            # 2. A human approves.
            mine[0].status = "approved"
            await db.commit()

        # 3. The same program now runs.
        second = await _runner()._run_python(CODE)
        assert second["status"] == "completed"
        assert sandbox == [CODE]

        # 4. A different program does not inherit that approval.
        other = await _runner()._run_python("import os; os.system('id')")
        assert other["status"] == "needs_approval"
        assert sandbox == [CODE]
    finally:
        async with get_db_context() as db:
            await _cleanup(db)


@pytest.mark.asyncio
async def test_auto_mode_runs_without_leaving_an_approval_record(sandbox):
    async with get_db_context() as db:
        await _cleanup(db)
    try:
        result = await _runner(mode="auto")._run_python(CODE)
        assert result["status"] == "completed"
        assert sandbox == [CODE]

        async with get_db_context() as db:
            rows = (await db.execute(select(ApprovalRequest).where(
                ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE,
            ))).scalars().all()
            assert [r for r in rows if (r.payload or {}).get("run_request_id") == RUN] == []
    finally:
        async with get_db_context() as db:
            await _cleanup(db)
