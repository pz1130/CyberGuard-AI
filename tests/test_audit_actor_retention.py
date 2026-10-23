"""A user cleanup must not rewrite an already signed audit actor."""
import uuid

import pytest
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.core import audit
from app.core.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.user import User


@pytest.mark.asyncio
@pytest.mark.parametrize('orm_delete', [False, True])
async def test_hard_deletion_is_rejected_and_soft_deactivation_preserves_signature(orm_delete):
    suffix = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        user = User(username=f'actor_{suffix}', email=f'{suffix}@example.org',
                    hashed_password='test-only', role='viewer', is_active=True)
        db.add(user)
        await db.commit()
        uid = user.id
    signed = await audit.record_action(user_id=uid, action='test.actor_retention')
    try:
        async with AsyncSessionLocal() as db:
            with pytest.raises(IntegrityError):
                if orm_delete:
                    user = await db.get(User, uid)
                    # Exercise an ORM deletion even with the relationship loaded.
                    await db.refresh(user, ['audit_logs'])
                    await db.delete(user)
                else:
                    await db.execute(delete(User).where(User.id == uid))
                await db.commit()
            await db.rollback()
            user = await db.get(User, uid)
            user.is_active = False
            await db.commit()
            row = (await db.execute(select(AuditLog).where(
                AuditLog.entry_hash == signed['entry_hash']))).scalar_one()
            assert row.user_id == uid
            assert audit.stamp_chain_hashes(audit._row_chain_payload(row), row.prev_hash)['entry_hash'] == row.entry_hash
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == uid))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
