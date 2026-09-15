"""Approval binds to one specific piece of code, in one specific run."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.database import get_db_context
from app.models.approval import ApprovalRequest
from app.services.code_approval import (
    CODE_APPROVAL_ACTION_TYPE,
    MAX_CODE_APPROVAL_ROUNDS,
    code_digest,
    code_approval_request_id,
    count_rounds,
    create_pending,
    find_approved,
)

RUN = "unit-code-run"
OTHER_RUN = "unit-code-run-other"


# --- digest ---

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


# --- the deterministic id, which is what makes the lookup indexed ---

def test_request_id_is_deterministic_and_fits_the_column():
    a = code_approval_request_id(RUN, code_digest("print(1)"))
    b = code_approval_request_id(RUN, code_digest("print(1)"))
    assert a == b
    assert len(a) == 36  # approval_requests.request_id is String(36)


def test_request_id_separates_runs_and_programs():
    d1, d2 = code_digest("print(1)"), code_digest("print(2)")
    assert code_approval_request_id(RUN, d1) != code_approval_request_id(RUN, d2)
    assert code_approval_request_id(RUN, d1) != code_approval_request_id(OTHER_RUN, d1)


# --- the queries, against a real database ---

async def _cleanup(db):
    for run in (RUN, OTHER_RUN):
        rows = (await db.execute(select(ApprovalRequest).where(
            ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE))).scalars().all()
        for r in rows:
            if (r.payload or {}).get("run_request_id") == run:
                await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id == r.id))
    await db.commit()


@pytest.mark.asyncio
async def test_a_pending_record_authorizes_nothing():
    code = "print('a')"
    async with get_db_context() as db:
        await _cleanup(db)
        try:
            await create_pending(db, request_id=RUN, digest=code_digest(code),
                                 code=code, user_id=1, agent_id=None, agent_name="a")
            assert await find_approved(db, RUN, code_digest(code)) is None
        finally:
            await _cleanup(db)


@pytest.mark.asyncio
async def test_an_approved_record_authorizes_only_that_code_in_that_run():
    code = "print('a')"
    digest = code_digest(code)
    async with get_db_context() as db:
        await _cleanup(db)
        try:
            record = await create_pending(db, request_id=RUN, digest=digest, code=code,
                                          user_id=1, agent_id=None, agent_name="a")
            row = (await db.execute(select(ApprovalRequest).where(
                ApprovalRequest.id == record.id))).scalar_one()
            row.status = "approved"
            await db.commit()

            assert await find_approved(db, RUN, digest) is not None
            assert await find_approved(db, RUN, code_digest("print('b')")) is None
            assert await find_approved(db, OTHER_RUN, digest) is None
        finally:
            await _cleanup(db)


@pytest.mark.asyncio
async def test_proposing_the_same_code_twice_reuses_one_record():
    # Otherwise a re-run would open a fresh pending approval every pass and
    # burn through the round cap without the model changing anything.
    code = "print('a')"
    async with get_db_context() as db:
        await _cleanup(db)
        try:
            first = await create_pending(db, request_id=RUN, digest=code_digest(code),
                                         code=code, user_id=1, agent_id=None, agent_name="a")
            second = await create_pending(db, request_id=RUN, digest=code_digest(code),
                                          code=code, user_id=1, agent_id=None, agent_name="a")
            assert first.id == second.id
            assert await count_rounds(db, RUN) == 1
        finally:
            await _cleanup(db)


@pytest.mark.asyncio
async def test_count_rounds_counts_only_this_run():
    async with get_db_context() as db:
        await _cleanup(db)
        try:
            for src in ("print(1)", "print(2)"):
                await create_pending(db, request_id=RUN, digest=code_digest(src), code=src,
                                     user_id=1, agent_id=None, agent_name="a")
            await create_pending(db, request_id=OTHER_RUN, digest=code_digest("print(3)"),
                                 code="print(3)", user_id=1, agent_id=None, agent_name="a")
            assert await count_rounds(db, RUN) == 2
            assert await count_rounds(db, OTHER_RUN) == 1
        finally:
            await _cleanup(db)
