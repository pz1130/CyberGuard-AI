"""Custom templates render as data, preserve saved mail settings, and validate."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.email_templates import render_notification, DEFAULT_TEMPLATES
from app.schemas.email_config import EmailConfigWrite, EmailTestRequest
from app.models.email_config import EmailConfig
from app.services.email_config import row_config


@pytest.mark.parametrize('key,value', [
    ('created_subject', 'Hello\r\nBcc: attacker@example.org'),
    ('created_body', '{{decision}}'), ('decided_body', '{{user_id}}'),
    ('created_body', '{{request_id.upper()}}'), ('created_body', '{{request_id'),
    ('decided_subject', ' '), ('created_body', ''),
])
def test_invalid_templates(key, value):
    with pytest.raises(ValidationError):
        EmailConfigWrite(**{key: value})


def test_custom_templates_escape_values_and_strip_subject_line_breaks():
    config = EmailConfigWrite(created_subject='审批 {{ request_id }}',
                            created_body='<div>{{action_description}}</div>').model_dump()
    subject, body = render_notification(config, 'created', {
        'request_id': 'abc\r\nBcc: bad', 'action_description': '<script>alert("x")</script>',
    })
    assert subject == '审批 abc  Bcc: bad'
    assert body == '<div>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</div>'


def test_old_saved_configs_receive_default_templates():
    row = EmailConfig(id=1, enabled=False, config_json={'method': 'smtp'},
                      smtp_password_encrypted=None, oauth_client_secret_encrypted=None)
    config = row_config(row)
    assert config['created_subject'] == DEFAULT_TEMPLATES['created_subject']
    assert config['template_defaults'] == DEFAULT_TEMPLATES
    subject, body = render_notification({}, 'decided', {'request_id': 'r', 'decision': 'APPROVED', 'comment': 'ok'})
    assert 'APPROVED' in subject and 'ok' in body


async def test_actual_notifications_use_custom_subject_and_body(monkeypatch):
    from app.services import email_service as service
    import app.services.email_config as config_service
    cfg = dict(enabled=True, method='smtp', from_email='sender@example.org', smtp_host='smtp.example.org',
               notify_created=True, notify_decided=True,
               created_subject='Review {{risk_level}}', created_body='<p>{{action_description}}</p>',
               decided_subject='Result {{decision}}', decided_body='<p>{{comment}}</p>')
    monkeypatch.setattr(config_service, 'load_email_config', AsyncMock(return_value=cfg))
    monkeypatch.setattr(config_service, 'approval_recipients', AsyncMock(return_value=['reviewer@example.org']))
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(service, 'send_email', sender)
    await service.notify_approval_created('req', 'scan host', 'high', 1)
    assert sender.await_args.args[:3] == ('reviewer@example.org', 'Review HIGH', '<p>scan host</p>')
    await service.notify_approval_decided('user@example.org', 'req', 'approved', 'reviewed')
    assert sender.await_args.args[:3] == ('user@example.org', 'Result APPROVED', '<p>reviewed</p>')


async def test_template_test_mail_uses_saved_template(monkeypatch):
    from app.routers.email_config import test_email
    from app.services import email_service
    import app.services.email_config as service
    cfg = {'created_subject': 'Sample {{request_id}}', 'created_body': '<p>{{risk_level}}</p>'}
    monkeypatch.setattr(service, 'load_email_config', AsyncMock(return_value=cfg))
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, 'send_email', sender)
    assert await test_email(EmailTestRequest(to_email='receiver@example.org', template='created'), None) == {'sent': True}
    assert sender.await_args.args == ('receiver@example.org', 'Sample sample-request-001', '<p>HIGH</p>')
