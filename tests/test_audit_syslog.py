"""Exercise actual Syslog transports without a database or external receiver."""
import asyncio
import json
import socket
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.schemas.audit import SyslogExportRequest
from app.services.audit_syslog import format_message, send_logs, SyslogExportError


def log_record():
    return SimpleNamespace(id=1, user_id=None, agent_id="测试", action="audit\nexport",
                           input_hash=None, output_hash=None, request_id=None,
                           prev_hash=None, entry_hash="abc", chain_version=2,
                           timestamp=datetime(2026, 9, 16, 12, 0))


def test_message_format():
    message = format_message(log_record(), 16)
    header, payload = message.decode().split(' - audit - ')
    assert header == '<134>1 2026-09-16T12:00:00+00:00 - cyberguard'
    assert b'\n' not in message
    assert json.loads(payload)['agent_id'] == '测试'
    assert json.loads(payload)['entry_hash'] == 'abc'


@pytest.mark.parametrize('params', [
    {'host': ' '}, {'host': 'https://example.com'}, {'host': 'a b'}, {'host': 'localhost:514'},
    {'host': 'localhost', 'port': 0}, {'host': 'localhost', 'port': 65536},
    {'host': 'localhost', 'protocol': 'http'}, {'host': 'localhost', 'facility': 24},
])
def test_invalid_config(params):
    with pytest.raises(ValidationError):
        SyslogExportRequest(**params)


async def test_udp_delivery():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', 0))
    receiver.setblocking(False)
    try:
        cfg = SyslogExportRequest(host='127.0.0.1', port=receiver.getsockname()[1], protocol='udp')
        assert await send_logs([log_record()], cfg) == 1
        message = await asyncio.wait_for(asyncio.get_running_loop().sock_recv(receiver, 65535), 2)
        assert message == format_message(log_record(), 16)
    finally:
        receiver.close()


async def test_tcp_delivery():
    received = asyncio.get_running_loop().create_future()

    async def collect(reader, writer):
        try:
            messages = []
            for _ in range(2):
                length = int(await reader.readuntil(b' '))
                messages.append(await reader.readexactly(length))
            received.set_result(messages)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(collect, '127.0.0.1', 0)
    async with server:
        cfg = SyslogExportRequest(host='127.0.0.1', port=server.sockets[0].getsockname()[1])
        assert await send_logs([log_record(), log_record()], cfg) == 2
        assert await asyncio.wait_for(received, 2) == [format_message(log_record(), 16)] * 2


async def test_failure_preserves_sent_count(monkeypatch):
    writer = SimpleNamespace(write=lambda _: None, drain=AsyncMock(side_effect=[None, OSError('failed')]),
                             close=lambda: None, wait_closed=AsyncMock())
    monkeypatch.setattr(asyncio, 'open_connection', AsyncMock(return_value=(None, writer)))
    with pytest.raises(SyslogExportError) as exc:
        await send_logs([log_record(), log_record()], SyslogExportRequest(host='localhost'))
    assert exc.value.sent == 1


async def test_export_endpoint(monkeypatch):
    from app.routers.audit import export_audit_logs_syslog
    import app.services.audit_syslog as service
    records = [log_record()]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: records))))
    sender = AsyncMock(return_value=1)
    monkeypatch.setattr(service, 'send_logs', sender)
    cfg = SyslogExportRequest(host='localhost')
    assert await export_audit_logs_syslog(cfg, db, None) == {'sent': 1, 'total': 1, 'protocol': 'tcp'}
    sender.assert_awaited_once_with(records, cfg)
    from fastapi import HTTPException
    sender.side_effect = SyslogExportError(0)
    with pytest.raises(HTTPException) as exc:
        await export_audit_logs_syslog(cfg, db, None)
    assert exc.value.status_code == 502
    assert exc.value.detail['sent'] == 0


async def test_empty_export_does_not_connect(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(asyncio, 'open_connection', connect)
    assert await send_logs([], SyslogExportRequest(host='localhost')) == 0
    connect.assert_not_awaited()


def test_ipv6_config():
    assert SyslogExportRequest(host='::1').host == '::1'
