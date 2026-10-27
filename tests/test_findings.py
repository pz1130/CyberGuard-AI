import hashlib
import uuid
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, delete

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.finding import Finding, FindingEvent
from app.models.audit import AuditLog
from app.routers.findings import router
from app.schemas.finding import FindingCreate, FindingChange
from app.services.findings import create_finding, change_finding, report_markdown


@pytest_asyncio.fixture
async def actors():
    token = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        rows = [User(username=f'finding_{role}_{token}', email=f'{role}_{token}@example.test',
                     hashed_password='unused', role=role, is_active=True)
                for role in ('operator', 'analyst', 'approver', 'viewer')]
        db.add_all(rows); await db.commit()
        result = [AuthenticatedUser(user_id=u.id, username=u.username, email=u.email, role=u.role) for u in rows]
    yield result
    ids = [u.user_id for u in result]
    async with AsyncSessionLocal() as db:
        finding_ids = select(Finding.id).where(Finding.created_by.in_(ids))
        await db.execute(delete(FindingEvent).where(FindingEvent.finding_id.in_(finding_ids)))
        await db.execute(delete(Finding).where(Finding.created_by.in_(ids)))
        await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(ids)))
        await db.execute(delete(User).where(User.id.in_(ids))); await db.commit()


def submission():
    return FindingCreate(title='Unescaped response', target='https://authorized.example', severity='high',
                         description='Response contains unescaped input', remediation='Encode output',
                         evidence='GET /example HTTP/1.1\r\n\r\n<script>example</script>\n')


async def apply(db, row, actor, action, **kwargs):
    return await change_finding(db, row.id, FindingChange(action=action, version=row.version,
                                note='Human review note', **kwargs), actor)


async def test_complete_workflow_retains_evidence_and_signed_history(actors):
    submitter, reviewer, approver, _ = actors
    async with AsyncSessionLocal() as db:
        row = await create_finding(db, submission(), submitter, agent_id=123)
        assert row.status == 'pending' and row.source == 'agent'
        await apply(db, row, reviewer, 'confirm')
        await apply(db, row, reviewer, 'assign', assignee_id=submitter.user_id)
        await apply(db, row, submitter, 'ready')
        await apply(db, row, approver, 'resolve', evidence='Retest: encoded response')
        assert row.status == 'resolved'
        await apply(db, row, approver, 'reopen', evidence='Regression reproduced')
        assert row.status == 'confirmed'
        events = (await db.execute(select(FindingEvent).where(FindingEvent.finding_id == row.id).order_by(FindingEvent.id))).scalars().all()
        assert len(events) == 6 and events[0].evidence == submission().evidence
        assert events[0].evidence_hash == hashlib.sha256(submission().evidence.encode()).hexdigest()
        audits = (await db.execute(select(AuditLog).where(AuditLog.request_id.in_([e.audit_request_id for e in events])))).scalars().all()
        assert len(audits) == 6
        from app.core.audit import stamp_chain_hashes, _row_chain_payload
        assert all(stamp_chain_hashes(_row_chain_payload(a), a.prev_hash)['entry_hash'] == a.entry_hash for a in audits)
        report = report_markdown(row, events)
        assert submission().evidence in report and 'Retest: encoded response' in report
        assert 'Regression reproduced' in report and events[0].audit_request_id in report


async def test_reject_invalid_transitions_stale_updates_and_self_review(actors):
    submitter, reviewer, _, viewer = actors
    async with AsyncSessionLocal() as db:
        row = await create_finding(db, submission(), reviewer)
        with pytest.raises(HTTPException) as error:
            await apply(db, row, reviewer, 'confirm')
        assert error.value.status_code == 403
        with pytest.raises(HTTPException):
            await apply(db, row, submitter, 'ready')
        with pytest.raises(HTTPException):
            await create_finding(db, submission(), viewer)
        with pytest.raises(HTTPException) as error:
            await change_finding(db, row.id, FindingChange(action='evidence', version=99, note='stale', evidence='x'), submitter)
        assert error.value.status_code == 409
        assert row.status == 'pending' and row.version == 1


async def test_retest_requires_evidence_and_independent_reviewer(actors):
    submitter, reviewer, approver, _ = actors
    async with AsyncSessionLocal() as db:
        row = await create_finding(db, submission(), submitter)
        await apply(db, row, approver, 'confirm')
        await apply(db, row, reviewer, 'assign', assignee_id=reviewer.user_id)
        await apply(db, row, reviewer, 'ready')
        with pytest.raises(HTTPException) as error:
            await apply(db, row, reviewer, 'resolve', evidence='self review')
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await apply(db, row, approver, 'resolve')
        assert error.value.status_code == 422
        assert row.status == 'ready_for_retest'


async def test_failure_to_write_audit_rolls_back_finding(actors):
    async with AsyncSessionLocal() as db:
        with patch('app.core.audit.stamp_chain_hashes', side_effect=RuntimeError('audit failed')):
            with pytest.raises(RuntimeError):
                await create_finding(db, submission(), actors[0])
        await db.rollback()
        assert not (await db.execute(select(Finding).where(Finding.created_by == actors[0].user_id))).scalars().all()


async def test_http_permission_and_report_download(actors):
    app = FastAPI(); app.include_router(router)
    actor = actors[0]
    app.dependency_overrides[get_current_user] = lambda: actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.post('/findings', json=submission().model_dump())
        assert result.status_code == 201, result.text
        finding_id = result.json()['id']
        assert (await client.get('/findings')).json()['total'] >= 1
        assert (await client.get('/findings?status=invalid')).status_code == 422
        export = await client.get(f'/findings/{finding_id}/report')
        assert export.status_code == 200 and 'attachment' in export.headers['content-disposition']
        actor = actors[3]
        assert (await client.get('/findings')).status_code == 403
        assert (await client.get(f'/findings/{finding_id}')).status_code == 403
        assert (await client.get(f'/findings/{finding_id}/report')).status_code == 403
        assert (await client.post('/findings', json=submission().model_dump())).status_code == 403


async def test_agent_cannot_submit_confirmation_or_impersonate_user(actors):
    from app.services.finding_tools import submit_from_agent, submission_tool
    import json
    assert await submission_tool(actors[3].user_id) is None
    assert (await submission_tool(actors[0].user_id))['function']['name'] == 'finding_submit'
    response = json.loads(await submit_from_agent(actors[0].user_id, 12, {**submission().model_dump(), 'status': 'resolved'}))
    assert response['status'] == 'error'
    response = json.loads(await submit_from_agent(actors[0].user_id, 12, submission().model_dump()))
    assert response['status'] == 'pending' and response['requires_human_review']


async def test_former_owner_cannot_review_after_handing_off(actors):
    """Reassigning away must not let the person who did the fix sign it off."""
    submitter, reviewer, approver, _ = actors
    async with AsyncSessionLocal() as db:
        row = await create_finding(db, submission(), submitter)
        await apply(db, row, approver, 'confirm')
        await apply(db, row, reviewer, 'assign', assignee_id=reviewer.user_id)
        await apply(db, row, reviewer, 'assign', assignee_id=submitter.user_id)
        await apply(db, row, submitter, 'ready')
        with pytest.raises(HTTPException) as error:
            await apply(db, row, reviewer, 'resolve', evidence='self review after hand-off')
        assert error.value.status_code == 403
        assert row.status == 'ready_for_retest'
        await apply(db, row, approver, 'resolve', evidence='Independent retest')
        assert row.status == 'resolved'
        finding_id = row.id

    app = FastAPI(); app.include_router(router)
    current = {'actor': reviewer}
    app.dependency_overrides[get_current_user] = lambda: current['actor']
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get(f'/findings/{finding_id}')).json()['independent_reviewer'] is False
        current['actor'] = approver
        assert (await client.get(f'/findings/{finding_id}')).json()['independent_reviewer'] is True


async def test_agent_submission_audit_names_the_agent(actors):
    """The signed audit row must say an agent submitted it, not only which user ran the agent."""
    from app.core.audit import stamp_chain_hashes, _row_chain_payload
    submitter, reviewer, _, _ = actors
    async with AsyncSessionLocal() as db:
        row = await create_finding(db, submission(), submitter, agent_id=123)
        await apply(db, row, reviewer, 'confirm')
        events = (await db.execute(select(FindingEvent).where(FindingEvent.finding_id == row.id)
                                   .order_by(FindingEvent.id))).scalars().all()
        audits = {a.request_id: a for a in (await db.execute(select(AuditLog).where(
            AuditLog.request_id.in_([e.audit_request_id for e in events])))).scalars().all()}
    submit, confirm = (audits[e.audit_request_id] for e in events)
    assert submit.action == 'finding.submit' and submit.agent_id == '123'
    assert confirm.action == 'finding.confirm' and confirm.agent_id is None
    assert all(stamp_chain_hashes(_row_chain_payload(a), a.prev_hash)['entry_hash'] == a.entry_hash
               for a in (submit, confirm))
