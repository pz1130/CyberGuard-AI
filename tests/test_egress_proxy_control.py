"""The grant/revoke control listener."""
from __future__ import annotations

import asyncio
import base64
import json
import os

import pytest

os.environ["EGRESS_PROXY_TOKEN"] = "control-token"

from egress_proxy import main as ep


@pytest.fixture(autouse=True)
def _clean_store():
    ep.STORE = ep.GrantStore()
    ep.CONTROL_TOKEN = "control-token"
    yield
    ep.STORE = ep.GrantStore()


async def _control(path: str, body: dict, token: str = "control-token") -> str:
    server = await ep.start_control("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        payload = json.dumps(body).encode()
        writer.write(
            f"POST {path} HTTP/1.1\r\nX-Egress-Token: {token}\r\n"
            f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(400), timeout=5)
        writer.close()
        return data.decode("latin1")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_grant_registers_an_allowlist():
    reply = await _control("/grant", {"nonce": "n1", "allowlist": ["v.example"], "ttl": 60})
    assert "200" in reply
    assert ep.STORE.lookup("n1") == ["v.example"]


@pytest.mark.asyncio
async def test_revoke_removes_it():
    await _control("/grant", {"nonce": "n1", "allowlist": ["v.example"], "ttl": 60})
    reply = await _control("/revoke", {"nonce": "n1"})
    assert "200" in reply
    assert ep.STORE.lookup("n1") is None


@pytest.mark.asyncio
async def test_wrong_token_is_rejected_and_grants_nothing():
    reply = await _control("/grant", {"nonce": "n1", "allowlist": ["v.example"], "ttl": 60},
                           token="wrong")
    assert "401" in reply
    assert ep.STORE.lookup("n1") is None


@pytest.mark.asyncio
async def test_grant_without_a_nonce_is_rejected():
    reply = await _control("/grant", {"allowlist": ["v.example"], "ttl": 60})
    assert "400" in reply


@pytest.mark.asyncio
async def test_grant_with_an_empty_allowlist_is_rejected():
    # An empty list would be a grant that permits nothing, which is a caller
    # bug worth surfacing rather than a silently useless execution.
    reply = await _control("/grant", {"nonce": "n1", "allowlist": [], "ttl": 60})
    assert "400" in reply
    assert ep.STORE.lookup("n1") is None


@pytest.mark.asyncio
async def test_grant_with_a_non_positive_ttl_is_rejected():
    reply = await _control("/grant", {"nonce": "n1", "allowlist": ["v.example"], "ttl": 0})
    assert "400" in reply
    assert ep.STORE.lookup("n1") is None


@pytest.mark.asyncio
async def test_unknown_path_is_404():
    reply = await _control("/whatever", {"nonce": "n1"})
    assert "404" in reply


@pytest.mark.asyncio
async def test_an_unconfigured_token_refuses_everything():
    # A proxy started without EGRESS_PROXY_TOKEN must not accept a blank token
    # as a match for its blank config.
    ep.CONTROL_TOKEN = ""
    reply = await _control("/grant", {"nonce": "n1", "allowlist": ["v.example"], "ttl": 60},
                           token="")
    assert "401" in reply
    assert ep.STORE.lookup("n1") is None


@pytest.mark.asyncio
async def test_the_control_token_does_not_open_the_proxy_port():
    # The control surface and the data surface are separate listeners on
    # purpose; holding the control token must not by itself grant egress.
    server = await ep.start_proxy("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        creds = base64.b64encode(b"control-token:x").decode()
        writer.write(
            f"CONNECT v.example:443 HTTP/1.1\r\n"
            f"Proxy-Authorization: Basic {creds}\r\n\r\n".encode())
        await writer.drain()
        reply = (await asyncio.wait_for(reader.read(200), timeout=5)).decode("latin1")
        writer.close()
        assert "407" in reply
    finally:
        server.close()
        await server.wait_closed()
