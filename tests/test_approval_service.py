"""Tests for ApprovalService — the human-in-the-loop CRUD + decision logic.

These exercise the real test DB (DATABASE_URL) since the table/columns and the
pending->approved/rejected state machine are exactly what's untested.  The
fire-and-forget side effects (Redis pub/sub and email) are patched out so
the tests stay deterministic and offline.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models.approval import ApprovalRequest
from app.services.approval_service import ApprovalService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _silence_side_effects():
    """Patch out Redis/email fan-out so create_request stays offline."""
    with patch.object(ApprovalService, "_publish", AsyncMock()), \
         patch.object(ApprovalService, "_publish_admin_event", AsyncMock()), \
         patch.object(ApprovalService, "_email_admin_created", AsyncMock()), \
         patch("app.services.email_service.notify_approval_created", AsyncMock()):
        yield


@pytest.fixture
async def cleanup_ids():
    """Collect request_ids created by a test and delete the rows afterwards."""
    ids: list[str] = []
    yield ids
    async with AsyncSessionLocal() as session:
        for rid in ids:
            await session.execute(
                delete(ApprovalRequest).where(ApprovalRequest.request_id == rid)
            )
        await session.commit()


async def _create(cleanup_ids, **overrides):
    rid = overrides.pop("request_id", str(uuid.uuid4()))  # request_id is VARCHAR(36)
    cleanup_ids.append(rid)
    kwargs = dict(
        request_id=rid,
        user_id=1,
        action_type="tool_exec",
        action_description="run nmap against target",
        risk_level="high",
    )
    kwargs.update(overrides)
    record = await ApprovalService.create_request(**kwargs)
    return rid, record


async def test_create_request_persists_pending(cleanup_ids):
    rid, record = await _create(cleanup_ids)
    assert record.id is not None
    assert record.status == "pending"
    assert record.risk_level == "high"
    assert record.approver_id is None
    assert record.decided_at is None

    fetched = await ApprovalService.get_by_request_id(rid)
    assert fetched is not None
    assert fetched.request_id == rid
    assert fetched.action_description == "run nmap against target"


async def test_list_pending_includes_new_request(cleanup_ids):
    rid, _ = await _create(cleanup_ids)
    pending = await ApprovalService.list_pending()
    assert rid in {r.request_id for r in pending}
    assert all(r.status == "pending" for r in pending)


async def test_decide_approved_updates_record(cleanup_ids):
    rid, record = await _create(cleanup_ids)
    updated = await ApprovalService.decide(
        rid, "approved", approver_id=7, comment="looks fine"
    )
    assert updated.status == "approved"
    assert updated.approver_id == 7
    assert updated.approver_comment == "looks fine"
    assert updated.decided_at is not None

    # No longer pending
    pending = await ApprovalService.list_pending()
    assert rid not in {r.request_id for r in pending}

    # Persisted
    refetched = await ApprovalService.get_by_id(record.id)
    assert refetched.status == "approved"


async def test_decide_rejected_updates_record(cleanup_ids):
    rid, _ = await _create(cleanup_ids)
    updated = await ApprovalService.decide(rid, "rejected", approver_id=3)
    assert updated.status == "rejected"
    assert updated.approver_id == 3
    assert updated.decided_at is not None


@pytest.mark.parametrize("decision", ["approved", "rejected"])
async def test_requester_cannot_decide_own_request(cleanup_ids, decision):
    from app.services.approval_service import SelfApprovalError

    rid, _ = await _create(cleanup_ids, user_id=7)
    with pytest.raises(SelfApprovalError):
        await ApprovalService.decide(rid, decision, approver_id=7)

    record = await ApprovalService.get_by_request_id(rid)
    assert record.status == "pending"
    assert record.approver_id is None
    assert record.decided_at is None


async def test_decide_invalid_decision_raises(cleanup_ids):
    rid, _ = await _create(cleanup_ids)
    with pytest.raises(ValueError, match="Invalid decision"):
        await ApprovalService.decide(rid, "maybe", approver_id=1)
    # Untouched — still pending
    assert (await ApprovalService.get_by_request_id(rid)).status == "pending"


async def test_decide_unknown_request_raises():
    with pytest.raises(ValueError, match="No pending approval request"):
        await ApprovalService.decide(f"missing-{uuid.uuid4()}", "approved", approver_id=1)


async def test_decide_twice_raises(cleanup_ids):
    rid, _ = await _create(cleanup_ids)
    await ApprovalService.decide(rid, "approved", approver_id=7)
    # Second decision finds no *pending* row → ValueError
    with pytest.raises(ValueError, match="No pending approval request"):
        await ApprovalService.decide(rid, "rejected", approver_id=2)


async def test_wait_for_decision_auto_approves(cleanup_ids, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "AUTO_APPROVE", True, raising=False)

    rid, _ = await _create(cleanup_ids)
    status, comment = await ApprovalService.wait_for_decision(rid, timeout_seconds=5)
    assert status == "approved"
    assert comment == "Auto-approved by system"
    # DB reflects the auto-decision
    assert (await ApprovalService.get_by_request_id(rid)).status == "approved"


async def test_expired_request_cannot_be_decided_even_without_cleanup(cleanup_ids):
    from app.services.approval_service import ApprovalExpiredError
    rid, _ = await _create(cleanup_ids, expires_in_minutes=-1)
    with pytest.raises(ApprovalExpiredError):
        await ApprovalService.decide(rid, 'approved', approver_id=7)
    record = await ApprovalService.get_by_request_id(rid)
    assert record.status == 'expired'
    assert record.approver_id is None and record.decided_at is None


async def test_expiry_cleanup_keeps_live_and_decided_requests(cleanup_ids):
    from datetime import timedelta
    from sqlalchemy import update
    from app.core.time import utc_now
    old, _ = await _create(cleanup_ids, expires_in_minutes=-1)
    live, _ = await _create(cleanup_ids)
    indefinite, _ = await _create(cleanup_ids, expires_in_minutes=None)
    decided, _ = await _create(cleanup_ids)
    await ApprovalService.decide(decided, 'approved', approver_id=7)
    async with AsyncSessionLocal() as session:
        await session.execute(update(ApprovalRequest).where(
            ApprovalRequest.request_id == decided).values(expires_at=utc_now()-timedelta(minutes=1)))
        await session.commit()
    await ApprovalService.expire_pending()
    pending = {r.request_id for r in await ApprovalService.list_pending()}
    assert old not in pending and live in pending and indefinite in pending
    assert (await ApprovalService.get_by_request_id(decided)).status == 'approved'


async def test_wait_returns_expired_without_waiting_full_timeout(cleanup_ids, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'AUTO_APPROVE', False)
    rid, _ = await _create(cleanup_ids, expires_in_minutes=-1)
    assert await ApprovalService.wait_for_decision(rid, timeout_seconds=30) == ('expired', None)


async def test_two_concurrent_decisions_allow_only_one(cleanup_ids):
    import asyncio
    rid, _ = await _create(cleanup_ids)
    results = await asyncio.gather(
        ApprovalService.decide(rid, 'approved', approver_id=7),
        ApprovalService.decide(rid, 'rejected', approver_id=8),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ApprovalRequest) for r in results) == 1
    assert sum(isinstance(r, ValueError) for r in results) == 1
