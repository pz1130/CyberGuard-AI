"""Tests for the hash-chained audit record_action() and verify_chain()."""
import pytest
from app.core import audit


@pytest.fixture(autouse=True)
async def uid():
    """Clean the hash chain and get-or-create a real user for the FK."""
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    from app.models.user import User
    from sqlalchemy import delete, select
    async with get_db_context() as s:
        await s.execute(delete(AuditLog).where(AuditLog.entry_hash.is_not(None)))
        user = (await s.execute(select(User).where(
            User.username == "audit-chain-test"))).scalar_one_or_none()
        if user is None:
            user = User(username="audit-chain-test",
                        email="audit-chain-test@example.com", role="admin")
            s.add(user)
        await s.commit()
        await s.refresh(user)
        user_id = user.id
    yield user_id


@pytest.mark.asyncio
async def test_record_action_chains_and_verifies(uid):
    a = await audit.record_action(
        user_id=uid, agent_name="threat_intel", action="isolate_host",
        action_category="contain_hard", risk_tier="high", confidence=0.91,
        human_reviewer="alice@ndb", rollback_possible=True,
        input_data={"host": "h1"}, output_data={"ok": True},
    )
    b = await audit.record_action(
        user_id=uid, agent_name="threat_intel", action="block_ip",
        action_category="contain_hard", risk_tier="high", confidence=0.88,
        human_reviewer=None, rollback_possible=True,
        input_data={"ip": "1.2.3.4"}, output_data={"ok": True},
    )
    assert b["prev_hash"] == a["entry_hash"]
    assert len(a["entry_hash"]) == 64
    assert a["input_hash"] and a["output_hash"]
    ok, broken_at = await audit.verify_chain()
    assert ok is True and broken_at is None


@pytest.mark.asyncio
async def test_tampering_breaks_verification(uid):
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    from sqlalchemy import select
    await audit.record_action(user_id=uid, action="a", action_category="observe",
                              input_data={"x": 1}, output_data={"y": 1})
    row = await audit.record_action(user_id=uid, action="b", action_category="observe",
                                    input_data={"x": 2}, output_data={"y": 2})
    async with get_db_context() as s:
        rec = (await s.execute(select(AuditLog).where(
            AuditLog.entry_hash == row["entry_hash"]))).scalar_one()
        rec.prev_hash = "deadbeef" * 8
        await s.commit()
    ok, broken_at = await audit.verify_chain()
    assert ok is False and broken_at is not None
