"""Mailbox validation, credential protection and delivery without external mail."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.auth import AuthenticatedUser
from app.core.dependencies import get_current_user
from app.core.rbac import Role, Permission, has_permission
from app.models.email_config import EmailConfig
from app.routers.email_config import save_email_config
from app.schemas.email_config import EmailConfigWrite
from app.services.email_config import row_config, public_config, config_status
from app.services import email_service as es


def smtp_config(**overrides):
    return dict(enabled=True, method='smtp', from_email='sender@example.org', smtp_host='smtp.example.org',
                smtp_port=587, smtp_security='starttls', smtp_username='sender', smtp_password='secret',
                notify_created=True, notify_decided=True, **overrides)


def test_approver_permission_is_separate():
    for role in Role:
        assert has_permission(role, Permission.APPROVAL_DECIDE) == (role in (Role.ADMIN, Role.APPROVER))
    assert not has_permission(Role.APPROVER, Permission.SETTINGS_WRITE)
    assert not has_permission(Role.APPROVER, Permission.USER_WRITE)


@pytest.mark.parametrize('payload', [
    {'enabled': True}, {'enabled': True, 'from_email': 'sender@example.org'},
    {'smtp_port': 0}, {'smtp_security': 'invalid'}, {'oauth_tenant_id': '../../token'},
    {'from_email': 'sender@example.org\r\nBcc:evil@example.org'},
    {'enabled': True, 'method': 'oauth', 'from_email': 'sender@example.org'},
])
def test_config_validation(payload):
    with pytest.raises(ValidationError):
        EmailConfigWrite(**payload)


async def test_save_encrypts_preserves_and_clears_secrets(monkeypatch):
    from app.core import audit
    monkeypatch.setattr(audit, 'record_action', AsyncMock())
    row = EmailConfig(id=1)
    db = SimpleNamespace(get=AsyncMock(return_value=row), commit=AsyncMock())
    actor = AuthenticatedUser(user_id=1, username='admin', email='admin@example.org', role='admin')
    result = await save_email_config(EmailConfigWrite(smtp_password='password', oauth_client_secret='client-secret'), db, actor)
    assert row.smtp_password_encrypted != 'password'
    assert row.oauth_client_secret_encrypted != 'client-secret'
    assert 'smtp_password' not in result
    assert 'oauth_client_secret' not in result
    assert 'client-secret' not in json.dumps(result)
    assert result['smtp_password_set'] and result['oauth_client_secret_set']
    assert row_config(row, secrets=True)['smtp_password'] == 'password'
    encrypted = row.smtp_password_encrypted
    await save_email_config(EmailConfigWrite(), db, actor)
    assert row.smtp_password_encrypted == encrypted
    await save_email_config(EmailConfigWrite(smtp_password='', oauth_client_secret=''), db, actor)
    assert row.smtp_password_encrypted is None
    assert row.oauth_client_secret_encrypted is None


def test_public_config_hides_environment_credentials():
    public = public_config(smtp_config(oauth_client_secret='oauth-secret'))
    assert 'smtp_password' not in public and 'oauth_client_secret' not in public
    assert public['smtp_password_set']


@pytest.mark.parametrize('security', ['starttls', 'ssl', 'none'])
def test_smtp_security_and_authentication(monkeypatch, security):
    connection = MagicMock()
    server = connection.__enter__.return_value
    server.sendmail.return_value = {}
    smtp = MagicMock(return_value=connection)
    smtp_ssl = MagicMock(return_value=connection)
    monkeypatch.setattr(es.smtplib, 'SMTP', smtp)
    monkeypatch.setattr(es.smtplib, 'SMTP_SSL', smtp_ssl)
    cfg = smtp_config(); cfg['smtp_security'] = security
    assert es._send_sync('receiver@example.org', 'subject', '<p>hello</p>', 'hello', cfg)
    assert smtp_ssl.called == (security == 'ssl')
    assert server.starttls.called == (security == 'starttls')
    server.login.assert_called_once_with('sender', 'secret')
    server.sendmail.return_value = {'receiver@example.org': (550, 'rejected')}
    assert not es._send_sync('receiver@example.org', 'subject', 'hello', 'hello', cfg)


async def test_microsoft_oauth_token_and_sendmail(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        if 'login.microsoftonline.com' in str(request.url):
            assert b'grant_type=client_credentials' in request.content
            assert b'client_secret=client-secret' in request.content
            return httpx.Response(200, json={'access_token': 'access-token'})
        assert request.headers['authorization'] == 'Bearer access-token'
        message = json.loads(request.content)['message']
        assert message['toRecipients'][0]['emailAddress']['address'] == 'receiver@example.org'
        return httpx.Response(202)
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(handle), **kwargs))
    cfg = dict(enabled=True, method='oauth', from_email='sender@example.org',
               oauth_tenant_id='00000000-0000-0000-0000-000000000001',
               oauth_client_id='00000000-0000-0000-0000-000000000002', oauth_client_secret='client-secret')
    assert await es.send_email('receiver@example.org', 'subject', 'hello', config=cfg)
    assert len(requests) == 2
    assert '/users/sender%40example.org/sendMail' in str(requests[1].url)


async def test_disabled_and_oauth_failures_do_not_send(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(es, '_send_oauth', send)
    assert not await es.send_email('receiver@example.org', 'subject', 'hello', config={'enabled': False})
    send.assert_not_awaited()
    cfg = dict(enabled=True, method='oauth', from_email='sender@example.org',
               oauth_tenant_id='tenant', oauth_client_id='client', oauth_client_secret='secret')
    send.side_effect = httpx.ConnectError('offline')
    assert not await es.send_email('receiver@example.org', 'subject', 'hello', config=cfg)


async def test_pending_and_decision_notifications_respect_toggles_and_escape(monkeypatch):
    import app.services.email_config as service
    cfg = smtp_config()
    monkeypatch.setattr(service, 'load_email_config', AsyncMock(return_value=cfg))
    monkeypatch.setattr(service, 'approval_recipients', AsyncMock(return_value=['admin@example.org', 'approver@example.org']))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(es, 'send_email', send)
    await es.notify_approval_created('req', '<script>alert(1)</script>', 'high', 1)
    assert send.await_count == 2
    assert '<script>' not in send.await_args.args[2]
    send.reset_mock()
    await es.notify_approval_decided('user@example.org', 'req', 'approved', '<b>comment</b>')
    assert send.await_args.args[0] == 'user@example.org'
    assert '&lt;b&gt;' in send.await_args.args[2]
    send.reset_mock()
    cfg['notify_created'] = False; cfg['notify_decided'] = False
    await es.notify_approval_created('req', 'action', 'high', 1)
    await es.notify_approval_decided('user@example.org', 'req', 'approved', '')
    send.assert_not_awaited()


@pytest.mark.parametrize('role', ['viewer', 'operator', 'analyst', 'auditor'])
async def test_approval_routes_reject_users_without_permission(role):
    from app.routers.approval import router
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id=1, username='user', email='user@example.org', role=role)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/approvals')).status_code == 403
        assert (await client.post('/approvals/1/decide', json={'decision': 'approved'})).status_code == 403


async def test_approver_can_list_but_cannot_configure_mailbox():
    from app.routers.approval import router as approvals
    from app.routers.email_config import router as mailbox
    from app.core.database import get_db_session
    app = FastAPI(); app.include_router(approvals); app.include_router(mailbox)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id=1, username='user', email='user@example.org', role='approver')
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))))
    async def session():
        yield db
    app.dependency_overrides[get_db_session] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/approvals')).status_code == 200
        assert (await client.get('/email/config')).status_code == 403
        assert (await client.put('/email/config', json={})).status_code == 403


@pytest.mark.parametrize('role', ['admin', 'approver'])
async def test_authorized_roles_can_decide_and_receive_audit_trace(monkeypatch, role):
    from app.routers.approval import router
    from app.core.database import get_db_session
    from app.core import audit
    from app.services.approval_service import ApprovalService
    from app.core.time import utc_now
    import app.routers.approval as routes
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id=2, username='reviewer', email='reviewer@example.org', role=role)
    record = SimpleNamespace(id=1, request_id='request', user_id=1, approver_id=2, agent_id=None,
        agent_name=None, action_type='tool.execute', action_description='review', payload={},
        risk_level='high', urgency='normal', status='pending', created_at=utc_now(),
        expires_at=None, decided_at=None, approver_comment=None)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record)))
    async def session():
        yield db
    app.dependency_overrides[get_db_session] = session
    async def decide(**kwargs):
        assert kwargs['approver_id'] == 2
        record.status = kwargs['decision']
        return record
    monkeypatch.setattr(ApprovalService, 'decide', AsyncMock(side_effect=decide))
    trace = AsyncMock()
    monkeypatch.setattr(audit, 'record_action', trace)
    monkeypatch.setattr(routes, '_notify_decision', AsyncMock())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/approvals/1/decide', json={'decision': 'approved'})
        assert response.status_code == 200
        assert response.json()['status'] == 'approved'
    assert trace.await_args.kwargs['action'] == 'approval.decide'
