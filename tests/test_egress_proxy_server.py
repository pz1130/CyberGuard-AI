"""The proxy listener: auth, port, host, resolved IP, then bytes."""
from __future__ import annotations

import asyncio
import base64
import socket
import threading

import pytest

from egress_proxy import main as ep
from egress_proxy.ssrf import BlockedError


def _auth(nonce: str) -> str:
    return "Basic " + base64.b64encode(f"{nonce}:x".encode()).decode()


@pytest.fixture(autouse=True)
def _clean_store():
    ep.STORE = ep.GrantStore()
    yield
    ep.STORE = ep.GrantStore()


async def _speak(request: str) -> str:
    """Send one request through the proxy and read the reply."""
    server = await ep.start_proxy("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(request.encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(400), timeout=5)
        writer.close()
        return data.decode("latin1")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_missing_credentials_get_407():
    reply = await _speak("CONNECT vendor.example:443 HTTP/1.1\r\n\r\n")
    assert "407" in reply


@pytest.mark.asyncio
async def test_unknown_nonce_gets_407():
    reply = await _speak(
        f"CONNECT vendor.example:443 HTTP/1.1\r\nProxy-Authorization: {_auth('nope')}\r\n\r\n")
    assert "407" in reply


@pytest.mark.asyncio
async def test_expired_nonce_gets_407():
    clock = {"t": 0.0}
    ep.STORE = ep.GrantStore(now=lambda: clock["t"])
    ep.STORE.grant("n1", ["vendor.example"], ttl=10)
    clock["t"] = 11.0
    reply = await _speak(
        f"CONNECT vendor.example:443 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "407" in reply


@pytest.mark.asyncio
async def test_host_outside_the_allowlist_gets_403():
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)
    reply = await _speak(
        f"CONNECT other.example:443 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "403" in reply


@pytest.mark.asyncio
async def test_another_nonces_host_is_refused():
    # The per-script property, asserted at the wire rather than in the store.
    ep.STORE.grant("n1", ["a.example"], ttl=60)
    ep.STORE.grant("n2", ["b.example"], ttl=60)
    reply = await _speak(
        f"CONNECT b.example:443 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "403" in reply


@pytest.mark.asyncio
async def test_disallowed_port_gets_403():
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)
    reply = await _speak(
        f"CONNECT vendor.example:22 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "403" in reply


@pytest.mark.asyncio
async def test_allowlisted_host_resolving_into_a_private_range_gets_403(monkeypatch):
    # The check that matters most: the name is allowed, the address is not.
    def blocked(_h):
        raise BlockedError("host vendor.example resolves to private/metadata IP 169.254.169.254")

    monkeypatch.setattr(ep, "resolve_and_check", blocked)
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)
    reply = await _speak(
        f"CONNECT vendor.example:443 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "403" in reply
    assert "169.254.169.254" in reply


@pytest.mark.asyncio
async def test_allowed_connect_tunnels_bytes_both_ways(monkeypatch):
    # A stand-in origin the proxy is allowed to reach.
    origin = socket.socket()
    origin.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    origin.bind(("127.0.0.1", 0))
    origin.listen(1)
    origin_port = origin.getsockname()[1]

    def serve():
        c, _ = origin.accept()
        c.sendall(b"ORIGIN-HELLO:" + c.recv(100))
        c.close()

    threading.Thread(target=serve, daemon=True).start()

    # Resolution is faked so the allowlist entry maps to our local origin.
    monkeypatch.setattr(ep, "resolve_and_check", lambda h: "127.0.0.1")
    monkeypatch.setattr(ep, "ALLOWED_PORTS", frozenset({80, 443, origin_port}))
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)

    server = await ep.start_proxy("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            f"CONNECT vendor.example:{origin_port} HTTP/1.1\r\n"
            f"Proxy-Authorization: {_auth('n1')}\r\n\r\n".encode())
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        assert b"200" in head

        writer.write(b"CLIENT-PING")
        await writer.drain()
        body = await asyncio.wait_for(reader.read(100), timeout=5)
        assert body == b"ORIGIN-HELLO:CLIENT-PING"
        writer.close()
    finally:
        server.close()
        await server.wait_closed()
        origin.close()


@pytest.mark.asyncio
async def test_malformed_request_line_gets_400():
    reply = await _speak("NONSENSE\r\n\r\n")
    assert "400" in reply


@pytest.mark.asyncio
async def test_non_basic_authorization_is_not_accepted():
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)
    reply = await _speak(
        "CONNECT vendor.example:443 HTTP/1.1\r\n"
        "Proxy-Authorization: Bearer n1\r\n\r\n")
    assert "407" in reply
