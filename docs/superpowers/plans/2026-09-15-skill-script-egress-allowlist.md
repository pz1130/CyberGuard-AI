# Per-Script Egress Allowlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an approved skill script reach a named set of hosts and nothing else, enforced per script rather than per deployment.

**Architecture:** A new `egress-proxy` container is the only thing on both the sandbox segment and a segment with internet access. A second runner service, `skill-runner-net`, runs the existing skill-runner image on that sandbox segment with no route out. Before dispatch the API registers a per-execution nonce with the proxy carrying that tool's allowlist, and passes the nonce to the runner as proxy credentials; the proxy authorizes each CONNECT by nonce, hostname and **resolved IP**.

**Tech Stack:** Python 3.11 asyncio (raw TCP proxy — CONNECT tunnelling is not something an ASGI framework can express), httpx, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-skill-script-egress-allowlist-design.md`

## Global Constraints

- `HTTP_PROXY` is **not** the control. The route table is. Nothing in this plan may rely on a script honoring the variable.
- `egress_proxy/` is standalone: it must **not** import from `app`, `agent_core`, `tool_runner` or `skill_runner` — the same rule those packages already follow.
- Phase 1 is not modified: the `skill-runner` service stays attached to `sandbox` **alone**, and INV-40 must keep passing unchanged.
- The proxy allows ports **80 and 443 only**.
- The proxy checks the **resolved IP**, then connects to that same IP. Never resolve a second time.
- Grants live in process memory with `ttl = run timeout + 30s`. The proxy therefore runs **`--workers 1`**, asserted by a test.
- `EGRESS_PROXY_TOKEN` is shared by `api` and `egress-proxy` only. Neither runner ever receives it.
- `MINIMAL_ENV` in the runner gains proxy variables **and nothing else**. No token, no secret.
- Phase 2 adds **no migration**: `script_network` and `script_network_allowlist` exist from `038_skill_script_tools`.
- Run the suite with `make test`. For one file: `make test-env-up`, then `DATABASE_URL=postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test REDIS_URL=redis://:cyberguard-test-only@localhost:56379/0 REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(python3 -c "print('0'*64)") SECRET_KEY=$(python3 -c "print('1'*64)") ENVIRONMENT=testing AUTO_APPROVE=false .venv/bin/python -m pytest <file> -v`. Pure-unit files (Tasks 1–4) need neither.

---

## File Structure

| File | Responsibility |
|---|---|
| `egress_proxy/ssrf.py` (create) | Blocked networks/hostnames; resolve a host and reject private, loopback, link-local and metadata addresses |
| `egress_proxy/grants.py` (create) | Nonce → allowlist store with TTL; hostname matching (exact / `.suffix`) |
| `egress_proxy/main.py` (create) | The proxy itself (auth → port → host → resolved IP → tunnel) and the grant/revoke control listener |
| `egress-proxy/Dockerfile`, `egress-proxy/requirements.lock` (create) | Its image — standard library only, no framework |
| `skill_runner/main.py` (modify) | Accept `proxy_url` and inject it into the child environment |
| `app/services/tool_executor.py` (modify) | Branch on `script_network`; grant → run → revoke |
| `app/routers/skills.py` (modify) | Accept and validate `allowlist` at promotion |
| `docker-compose.yml` (modify) | `sandbox-net` + `egress` networks, `skill-runner-net`, `egress-proxy` |
| `tests/test_invariants_static.py` (modify) | INV-41 topology, blocklist parity, single worker |

---

### Task 1: SSRF floor for the proxy

**Files:**
- Create: `egress_proxy/__init__.py`, `egress_proxy/ssrf.py`
- Test: `tests/test_egress_proxy_ssrf.py`, `tests/test_invariants_static.py`

**Interfaces:**
- Produces:
  - `BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network]`
  - `BLOCKED_HOSTNAMES: frozenset[str]`
  - `BlockedError(Exception)`
  - `resolve_and_check(host: str) -> str` — returns the resolved IP as a string, raises `BlockedError`

- [ ] **Step 1: Write the failing test**

Create `tests/test_egress_proxy_ssrf.py`:

```python
"""The proxy's SSRF floor. An allowlisted name must not become a door inward."""
from __future__ import annotations

import pytest

from egress_proxy.ssrf import BlockedError, resolve_and_check


def test_rejects_metadata_hostnames_before_dns():
    for host in ("169.254.169.254", "metadata.google.internal", "localhost"):
        with pytest.raises(BlockedError):
            resolve_and_check(host)


def test_rejects_a_name_that_resolves_into_a_private_range(monkeypatch):
    # The whole point: the admin allowlisted vendor.example, but the attacker
    # controls that name and points it at the cloud metadata service.
    monkeypatch.setattr(
        "egress_proxy.ssrf._resolve", lambda h: "169.254.169.254")
    with pytest.raises(BlockedError, match="169.254.169.254"):
        resolve_and_check("vendor.example")


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.2.3", "172.16.0.5", "192.168.1.1", "0.0.0.0",
    "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1",
])
def test_rejects_every_blocked_range(monkeypatch, ip):
    monkeypatch.setattr("egress_proxy.ssrf._resolve", lambda h: ip)
    with pytest.raises(BlockedError):
        resolve_and_check("vendor.example")


def test_allows_a_public_address_and_returns_it(monkeypatch):
    monkeypatch.setattr("egress_proxy.ssrf._resolve", lambda h: "93.184.216.34")
    assert resolve_and_check("vendor.example") == "93.184.216.34"


def test_unresolvable_host_is_blocked_not_crashed(monkeypatch):
    def boom(_h):
        raise OSError("nodename nor servname provided")
    monkeypatch.setattr("egress_proxy.ssrf._resolve", boom)
    with pytest.raises(BlockedError):
        resolve_and_check("nope.invalid")
```

Append to `tests/test_invariants_static.py`:

```python
# --------------------------------------------------------------------------
# INV-41 · the proxy's blocklist may not drift from the app's
# --------------------------------------------------------------------------

def test_inv41_proxy_blocklist_matches_the_app_blocklist():
    """INV-41: egress_proxy cannot import app, so the blocklist exists twice.

    A security blocklist kept in two places drifts. This fails the moment
    someone tightens one copy and forgets the other.
    """
    from app.core import ssrf as app_ssrf
    from egress_proxy import ssrf as proxy_ssrf

    assert [str(n) for n in proxy_ssrf.BLOCKED_NETWORKS] == \
           [str(n) for n in app_ssrf._BLOCKED_NETWORKS]
    assert proxy_ssrf.BLOCKED_HOSTNAMES == app_ssrf._BLOCKED_HOSTNAMES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_ssrf.py tests/test_invariants_static.py -k "egress_proxy or inv41" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'egress_proxy'`

- [ ] **Step 3: Write minimal implementation**

Create `egress_proxy/__init__.py` (empty file).

Create `egress_proxy/ssrf.py`:

```python
"""SSRF floor for the egress proxy.

Standalone by design: this package must not import from ``app`` (the rule
``tool_runner`` and ``skill_runner`` already follow), so the blocklist is
restated here. INV-41 asserts the two copies stay identical.
"""
from __future__ import annotations

import ipaddress
import socket

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/32"),       # unspecified (binds to all local interfaces)
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),    # link-local + cloud metadata
    ipaddress.ip_network("::/128"),            # IPv6 unspecified
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6 (covers ::ffff:127.0.0.1 etc.)
]

BLOCKED_HOSTNAMES = frozenset({
    "169.254.169.254",          # AWS / Azure metadata
    "metadata.google.internal",  # GCP metadata
    "metadata.internal",
    "metadata.azure.com",
    "localhost",
    "0.0.0.0",
    "127.0.0.1",
})


class BlockedError(Exception):
    """The destination is not one this proxy will open."""


def _resolve(host: str) -> str:
    """Resolve a hostname to a single IP string. Seam for tests."""
    return socket.getaddrinfo(host, None)[0][4][0]


def resolve_and_check(host: str) -> str:
    """Resolve *host* and return its IP, or raise BlockedError.

    The caller must connect to the returned IP rather than to the name.
    Resolving a second time would reopen the DNS-rebinding hole this closes.
    """
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        raise BlockedError("empty host")
    if name in BLOCKED_HOSTNAMES:
        raise BlockedError(f"host {name} is blocked")

    try:
        ip_text = _resolve(name)
    except OSError as e:
        raise BlockedError(f"cannot resolve {name}: {e}") from e

    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError as e:
        raise BlockedError(f"{name} resolved to an unusable address {ip_text!r}") from e

    for net in BLOCKED_NETWORKS:
        if ip.version == net.version and ip in net:
            raise BlockedError(
                f"host {name} resolves to private/metadata IP {ip_text}")
    return ip_text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_ssrf.py -v && .venv/bin/python -m pytest tests/test_invariants_static.py -k inv41 -v`
Expected: 13 passed, then 1 passed

- [ ] **Step 5: Commit**

```bash
git add egress_proxy/__init__.py egress_proxy/ssrf.py tests/test_egress_proxy_ssrf.py tests/test_invariants_static.py
git commit -m "feat: add the egress proxy SSRF floor

An allowlisted hostname must not become a door inward: the check is on
the resolved IP, and INV-41 pins the duplicated blocklist to the app's."
```

---

### Task 2: Grant store and hostname matching

**Files:**
- Create: `egress_proxy/grants.py`
- Test: `tests/test_egress_proxy_grants.py`

**Interfaces:**
- Produces:
  - `host_allowed(host: str, allowlist: Sequence[str]) -> bool`
  - `GrantStore` with `grant(nonce: str, allowlist: list[str], ttl: float) -> None`, `revoke(nonce: str) -> None`, `lookup(nonce: str) -> list[str] | None` (None when missing or expired), `purge() -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_egress_proxy_grants.py`:

```python
"""Per-execution grants and hostname matching."""
from __future__ import annotations

import pytest

from egress_proxy.grants import GrantStore, host_allowed


@pytest.mark.parametrize("host,allowed", [
    ("vendor.example", True),
    ("VENDOR.EXAMPLE", True),          # case-insensitive
    ("vendor.example.", True),         # trailing dot
    ("api.vendor.example", False),     # exact entry does not cover subdomains
    ("evilvendor.example", False),     # not a suffix match on a label boundary
    ("other.example", False),
])
def test_exact_entries_match_only_that_host(host, allowed):
    assert host_allowed(host, ["vendor.example"]) is allowed


@pytest.mark.parametrize("host,allowed", [
    ("api.vendor.example", True),
    ("deep.api.vendor.example", True),
    ("vendor.example", True),          # the bare domain is covered too
    ("evilvendor.example", False),     # must not match without the dot
    ("vendor.example.evil.com", False),
])
def test_dot_prefixed_entries_match_the_suffix(host, allowed):
    assert host_allowed(host, [".vendor.example"]) is allowed


def test_empty_allowlist_permits_nothing():
    assert host_allowed("vendor.example", []) is False


def test_grant_lookup_and_revoke():
    store = GrantStore()
    store.grant("n1", ["vendor.example"], ttl=60)
    assert store.lookup("n1") == ["vendor.example"]
    store.revoke("n1")
    assert store.lookup("n1") is None


def test_unknown_nonce_is_none():
    assert GrantStore().lookup("never-granted") is None


def test_expired_grant_is_none(monkeypatch):
    clock = {"t": 1000.0}
    store = GrantStore(now=lambda: clock["t"])
    store.grant("n1", ["vendor.example"], ttl=30)
    clock["t"] = 1029.0
    assert store.lookup("n1") == ["vendor.example"]
    clock["t"] = 1031.0
    assert store.lookup("n1") is None


def test_purge_drops_expired_entries():
    clock = {"t": 0.0}
    store = GrantStore(now=lambda: clock["t"])
    store.grant("a", ["x.example"], ttl=10)
    store.grant("b", ["y.example"], ttl=100)
    clock["t"] = 50.0
    store.purge()
    assert store.lookup("a") is None
    assert store.lookup("b") == ["y.example"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_grants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'egress_proxy.grants'`

- [ ] **Step 3: Write minimal implementation**

Create `egress_proxy/grants.py`:

```python
"""Per-execution egress grants.

A grant is the whole authorization: it names one execution's allowlist and
expires with that execution. Nothing here is persisted — a proxy restart
drops every grant, and scripts lose network rather than gaining it.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple


def host_allowed(host: str, allowlist: Sequence[str]) -> bool:
    """Exact match, or suffix match for a leading-dot entry.

    Same rule as ``app/core/egress.py``; reimplemented because this package
    cannot import from ``app``.
    """
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        return False
    for raw in allowlist or ():
        entry = (raw or "").strip().lower().rstrip(".")
        if not entry:
            continue
        if entry.startswith("."):
            bare = entry[1:]
            if name == bare or name.endswith(entry):
                return True
        elif name == entry:
            return True
    return False


class GrantStore:
    """nonce -> (allowlist, expiry). In-memory, single process (see spec §4)."""

    def __init__(self, now: Optional[Callable[[], float]] = None) -> None:
        self._now = now or time.monotonic
        self._grants: Dict[str, Tuple[List[str], float]] = {}

    def grant(self, nonce: str, allowlist: List[str], ttl: float) -> None:
        self._grants[nonce] = (list(allowlist), self._now() + float(ttl))

    def revoke(self, nonce: str) -> None:
        self._grants.pop(nonce, None)

    def lookup(self, nonce: str) -> Optional[List[str]]:
        entry = self._grants.get(nonce)
        if not entry:
            return None
        allowlist, expiry = entry
        if self._now() > expiry:
            self._grants.pop(nonce, None)
            return None
        return allowlist

    def purge(self) -> None:
        now = self._now()
        for nonce in [n for n, (_a, exp) in self._grants.items() if now > exp]:
            self._grants.pop(nonce, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_grants.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add egress_proxy/grants.py tests/test_egress_proxy_grants.py
git commit -m "feat: add per-execution egress grants"
```

---

### Task 3: The proxy listener

**Files:**
- Create: `egress_proxy/main.py`
- Test: `tests/test_egress_proxy_server.py`

**Interfaces:**
- Consumes: `egress_proxy.ssrf.resolve_and_check`, `BlockedError`; `egress_proxy.grants.GrantStore`, `host_allowed`
- Produces:
  - `ALLOWED_PORTS: frozenset[int]` = `{80, 443}`
  - `STORE: GrantStore` — the process-wide store
  - `async handle_proxy(reader, writer) -> None`
  - `async start_proxy(host: str, port: int) -> asyncio.AbstractServer`

- [ ] **Step 1: Write the failing test**

Create `tests/test_egress_proxy_server.py`:

```python
"""The proxy listener: auth, port, host, resolved IP, then bytes."""
from __future__ import annotations

import asyncio
import base64
import socket

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
        data = await asyncio.wait_for(reader.read(200), timeout=5)
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
async def test_disallowed_port_gets_403():
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)
    reply = await _speak(
        f"CONNECT vendor.example:22 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "403" in reply


@pytest.mark.asyncio
async def test_allowlisted_host_resolving_into_a_private_range_gets_403(monkeypatch):
    # The check that matters most: the name is allowed, the address is not.
    monkeypatch.setattr(ep, "resolve_and_check",
                        lambda h: (_ for _ in ()).throw(BlockedError("private")))
    ep.STORE.grant("n1", ["vendor.example"], ttl=60)
    reply = await _speak(
        f"CONNECT vendor.example:443 HTTP/1.1\r\nProxy-Authorization: {_auth('n1')}\r\n\r\n")
    assert "403" in reply


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

    import threading
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'egress_proxy.main'`

- [ ] **Step 3: Write minimal implementation**

Create `egress_proxy/main.py`:

```python
"""Forward proxy for sandboxed skill scripts.

A raw asyncio server rather than an ASGI app: CONNECT tunnelling is not
something an HTTP framework can express.

This process is the only route out of the sandbox segment. The environment
variable HTTP_PROXY is a convenience for well-behaved clients; the actual
boundary is that the sandbox has no other route, so a script that ignores
the variable reaches nothing at all.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import List, Optional, Tuple

from egress_proxy.grants import GrantStore, host_allowed
from egress_proxy.ssrf import BlockedError, resolve_and_check

logger = logging.getLogger("egress-proxy")

ALLOWED_PORTS = frozenset({80, 443})
MAX_HEADER_BYTES = 16384
STORE = GrantStore()


def _nonce_from_headers(headers: List[str]) -> Optional[str]:
    """Pull the nonce out of Proxy-Authorization: Basic base64(nonce:x)."""
    for line in headers:
        name, _, value = line.partition(":")
        if name.strip().lower() != "proxy-authorization":
            continue
        scheme, _, blob = value.strip().partition(" ")
        if scheme.lower() != "basic":
            return None
        try:
            decoded = base64.b64decode(blob, validate=True).decode("utf-8", "replace")
        except Exception:
            return None
        return decoded.split(":", 1)[0] or None
    return None


def _split_host_port(target: str, default_port: int) -> Tuple[str, int]:
    if target.startswith("["):  # bracketed IPv6 literal
        host, _, rest = target[1:].partition("]")
        port = int(rest[1:]) if rest.startswith(":") and rest[1:].isdigit() else default_port
        return host, port
    host, sep, port_text = target.rpartition(":")
    if sep and port_text.isdigit():
        return host, int(port_text)
    return target, default_port


async def _deny(writer: asyncio.StreamWriter, status: str, detail: str) -> None:
    body = detail.encode()
    extra = ""
    if status.startswith("407"):
        extra = 'Proxy-Authenticate: Basic realm="egress"\r\n'
    writer.write(
        f"HTTP/1.1 {status}\r\n{extra}Content-Length: {len(body)}\r\n"
        f"Content-Type: text/plain\r\nConnection: close\r\n\r\n".encode() + body)
    try:
        await writer.drain()
    except ConnectionError:
        pass
    writer.close()


async def _pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
            await dst.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def handle_proxy(reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter) -> None:
    try:
        head = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"), timeout=30)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError,
            asyncio.LimitOverrunError, ConnectionError):
        writer.close()
        return
    if len(head) > MAX_HEADER_BYTES:
        await _deny(writer, "431 Request Header Fields Too Large", "headers too large")
        return

    lines = head.decode("latin1").split("\r\n")
    request_line, headers = lines[0], [line for line in lines[1:] if line]
    parts = request_line.split()
    if len(parts) != 3:
        await _deny(writer, "400 Bad Request", "malformed request line")
        return
    method, target, _version = parts

    nonce = _nonce_from_headers(headers)
    allowlist = STORE.lookup(nonce) if nonce else None
    if allowlist is None:
        await _deny(writer, "407 Proxy Authentication Required",
                    "no live egress grant for these credentials")
        return

    if method.upper() == "CONNECT":
        host, port = _split_host_port(target, 443)
    else:
        # Absolute-form: GET http://host/path HTTP/1.1
        scheme, _, rest = target.partition("://")
        if not rest:
            await _deny(writer, "400 Bad Request", "proxy requires absolute-form or CONNECT")
            return
        authority, _, _path = rest.partition("/")
        host, port = _split_host_port(authority, 443 if scheme == "https" else 80)

    if port not in ALLOWED_PORTS:
        await _deny(writer, "403 Forbidden", f"port {port} is not permitted")
        return
    if not host_allowed(host, allowlist):
        await _deny(writer, "403 Forbidden", f"host {host} is not on this script's allowlist")
        return
    try:
        ip = resolve_and_check(host)
    except BlockedError as e:
        await _deny(writer, "403 Forbidden", str(e))
        return

    try:
        # Connect to the address already validated — resolving again here is
        # exactly the DNS-rebinding window this design closes.
        up_reader, up_writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=15)
    except (OSError, asyncio.TimeoutError) as e:
        await _deny(writer, "502 Bad Gateway", f"cannot reach {host}: {e}")
        return

    if method.upper() == "CONNECT":
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
    else:
        # Rewrite to origin-form and drop hop-by-hop proxy headers.
        _scheme, _, rest = target.partition("://")
        _authority, _, path = rest.partition("/")
        forwarded = [f"{method} /{path} HTTP/1.1"]
        forwarded += [h for h in headers
                      if not h.split(":", 1)[0].strip().lower().startswith("proxy-")]
        up_writer.write(("\r\n".join(forwarded) + "\r\n\r\n").encode("latin1"))
        await up_writer.drain()

    await asyncio.gather(
        _pump(reader, up_writer),
        _pump(up_reader, writer),
        return_exceptions=True,
    )


async def start_proxy(host: str, port: int) -> asyncio.AbstractServer:
    return await asyncio.start_server(handle_proxy, host, port)


async def main() -> None:  # pragma: no cover - process entry point
    logging.basicConfig(level=logging.INFO)
    proxy = await start_proxy("0.0.0.0", int(os.environ.get("PROXY_PORT", "3128")))
    logger.info("egress proxy listening")
    async with proxy:
        await proxy.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_server.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add egress_proxy/main.py tests/test_egress_proxy_server.py
git commit -m "feat: add the egress proxy listener

Authorizes each CONNECT by nonce, port, hostname and resolved IP, then
connects to that same IP — resolving again would reopen the rebinding
window the check just closed."
```

---

### Task 4: Grant/revoke control listener

**Files:**
- Modify: `egress_proxy/main.py`
- Test: `tests/test_egress_proxy_control.py`

**Interfaces:**
- Produces:
  - `CONTROL_TOKEN: str` (from `EGRESS_PROXY_TOKEN`)
  - `async handle_control(reader, writer) -> None`
  - `async start_control(host: str, port: int) -> asyncio.AbstractServer`
  - Wire protocol: `POST /grant` with JSON `{"nonce": str, "allowlist": [str], "ttl": number}` and header `X-Egress-Token`; `POST /revoke` with `{"nonce": str}`. Replies `200 {"ok": true}`, `401`, or `400`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_egress_proxy_control.py`:

```python
"""The grant/revoke control listener."""
from __future__ import annotations

import asyncio
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
async def test_unknown_path_is_404():
    reply = await _control("/whatever", {"nonce": "n1"})
    assert "404" in reply
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_control.py -v`
Expected: FAIL — `AttributeError: module 'egress_proxy.main' has no attribute 'start_control'`

- [ ] **Step 3: Write minimal implementation**

In `egress_proxy/main.py`, add `import json` to the imports, then add after `STORE = GrantStore()`:

```python
CONTROL_TOKEN = os.environ.get("EGRESS_PROXY_TOKEN", "")
```

and add before `async def start_proxy`:

```python
async def _control_reply(writer: asyncio.StreamWriter, status: str, obj: dict) -> None:
    body = json.dumps(obj).encode()
    writer.write(
        f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
    try:
        await writer.drain()
    except ConnectionError:
        pass
    writer.close()


async def handle_control(reader: asyncio.StreamReader,
                         writer: asyncio.StreamWriter) -> None:
    """Grant and revoke. Separate listener from the proxy port so that the
    control surface and the data surface cannot be confused for each other."""
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError,
            asyncio.LimitOverrunError, ConnectionError):
        writer.close()
        return

    lines = head.decode("latin1").split("\r\n")
    parts = lines[0].split()
    if len(parts) != 3:
        await _control_reply(writer, "400 Bad Request", {"error": "malformed request"})
        return
    _method, path, _version = parts

    token, length = "", 0
    for line in lines[1:]:
        name, _, value = line.partition(":")
        key = name.strip().lower()
        if key == "x-egress-token":
            token = value.strip()
        elif key == "content-length" and value.strip().isdigit():
            length = int(value.strip())

    if not CONTROL_TOKEN or token != CONTROL_TOKEN:
        await _control_reply(writer, "401 Unauthorized", {"error": "bad control token"})
        return

    try:
        raw = await asyncio.wait_for(reader.readexactly(length), timeout=15) if length else b"{}"
        body = json.loads(raw or b"{}")
    except Exception:
        await _control_reply(writer, "400 Bad Request", {"error": "bad JSON body"})
        return
    if not isinstance(body, dict):
        await _control_reply(writer, "400 Bad Request", {"error": "body must be an object"})
        return

    nonce = body.get("nonce")
    if not nonce or not isinstance(nonce, str):
        await _control_reply(writer, "400 Bad Request", {"error": "nonce is required"})
        return

    if path == "/grant":
        allowlist = body.get("allowlist")
        if not isinstance(allowlist, list) or not allowlist:
            await _control_reply(writer, "400 Bad Request",
                                 {"error": "allowlist must be a non-empty list"})
            return
        try:
            ttl = float(body.get("ttl") or 0)
        except (TypeError, ValueError):
            ttl = 0.0
        if ttl <= 0:
            await _control_reply(writer, "400 Bad Request", {"error": "ttl must be positive"})
            return
        STORE.purge()
        STORE.grant(nonce, [str(h) for h in allowlist], ttl)
        await _control_reply(writer, "200 OK", {"ok": True})
        return

    if path == "/revoke":
        STORE.revoke(nonce)
        await _control_reply(writer, "200 OK", {"ok": True})
        return

    await _control_reply(writer, "404 Not Found", {"error": "unknown path"})


async def start_control(host: str, port: int) -> asyncio.AbstractServer:
    return await asyncio.start_server(handle_control, host, port)
```

Then replace `main()` with:

```python
async def main() -> None:  # pragma: no cover - process entry point
    logging.basicConfig(level=logging.INFO)
    if not CONTROL_TOKEN:
        raise RuntimeError("EGRESS_PROXY_TOKEN must be set for the egress proxy")
    proxy = await start_proxy("0.0.0.0", int(os.environ.get("PROXY_PORT", "3128")))
    control = await start_control("0.0.0.0", int(os.environ.get("CONTROL_PORT", "3129")))
    logger.info("egress proxy listening; control plane up")
    async with proxy, control:
        await asyncio.gather(proxy.serve_forever(), control.serve_forever())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_egress_proxy_control.py tests/test_egress_proxy_server.py -v`
Expected: 6 + 7 passed

- [ ] **Step 5: Commit**

```bash
git add egress_proxy/main.py tests/test_egress_proxy_control.py
git commit -m "feat: add the egress proxy control plane"
```

---

### Task 5: Image, compose services, network split

**Files:**
- Create: `egress-proxy/Dockerfile`, `egress-proxy/requirements.lock`
- Modify: `docker-compose.yml`, `.env.example`
- Test: `tests/test_invariants_static.py`

**Interfaces:**
- Produces: compose services `skill-runner-net` and `egress-proxy`; networks `sandbox-net` (internal) and `egress`; `api` env `SKILL_RUNNER_NET_URL`, `EGRESS_PROXY_CONTROL_URL`, `EGRESS_PROXY_URL`, `EGRESS_PROXY_TOKEN`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_invariants_static.py`:

```python
def test_inv41_egress_proxy_is_the_only_way_out_of_the_sandbox():
    """INV-41: the sandbox segments reach the internet only through the proxy."""
    compose = _compose()
    services, networks = compose["services"], compose["networks"]

    for name in ("skill-runner-net", "egress-proxy"):
        assert name in services, f"{name} service is missing"

    runner_nets = set(services["skill-runner-net"].get("networks") or [])
    proxy_nets = set(services["egress-proxy"].get("networks") or [])

    # The net-enabled runner has no route of its own.
    assert runner_nets == {"sandbox-net"}
    assert networks["sandbox-net"].get("internal") is True

    # The proxy bridges the sandbox to the outside and touches nothing else.
    assert proxy_nets == {"sandbox-net", "egress"}
    assert networks["egress"].get("internal") is not True
    for forbidden in ("backend", "sandbox"):
        assert forbidden not in proxy_nets
        assert forbidden not in runner_nets

    # Phase 1's no-network runner must not gain a path to the proxy.
    assert set(services["skill-runner"].get("networks") or []) == {"sandbox"}

    # api is the only service that must span both sandbox segments; without
    # this it cannot dispatch to either runner and nothing works at all.
    api_nets = set(services["api"].get("networks") or [])
    assert {"backend", "sandbox", "sandbox-net"} <= api_nets
    assert "egress" not in api_nets

    # Data plane stays where it was.
    for data_service in ("postgres", "redis"):
        nets = set(services[data_service].get("networks") or [])
        assert not (nets & (runner_nets | proxy_nets))


def test_inv41_runners_never_receive_the_control_token():
    services = _compose()["services"]
    for runner in ("skill-runner", "skill-runner-net"):
        env = services[runner].get("environment") or {}
        keys = set(env if isinstance(env, dict) else [e.split("=", 1)[0] for e in env])
        assert "EGRESS_PROXY_TOKEN" not in keys, f"{runner} must not hold the control token"
        assert "RUNNER_TOKEN" not in keys
        assert "env_file" not in services[runner]


def test_inv41_proxy_runs_a_single_worker():
    """Grants live in process memory, so a second worker would break lookups
    intermittently — which reads as a flaky 407, not as a config error.

    The service runs the module directly, so today there is no worker flag to
    get wrong. This guards the migration someone will eventually make to an
    ASGI server, where --workers N is the natural default.
    """
    svc = _compose()["services"]["egress-proxy"]
    command = svc.get("command")
    text = " ".join(command) if isinstance(command, list) else (command or "")
    assert "--workers" not in text or "--workers 1" in text
    assert "python" in text or "egress_proxy" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_invariants_static.py -k inv41 -v`
Expected: FAIL — `skill-runner-net service is missing`

- [ ] **Step 3: Write minimal implementation**

Create `egress-proxy/requirements.lock`:

```
# The egress proxy is standard library only. This file exists so the image
# build has the same shape as the other services; adding a dependency here
# means adding one to the one process that talks to the internet.
```

Create `egress-proxy/Dockerfile`:

```dockerfile
FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

WORKDIR /app

# No pip install: this service uses the standard library only. The one process
# with internet access is the one that should carry the least code.
COPY egress_proxy/ ./egress_proxy/

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 cyberguard \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin cyberguard

USER 10001:10001

EXPOSE 3128 3129
CMD ["python", "-m", "egress_proxy.main"]
```

In `docker-compose.yml`:

1. Add to the `api` service's `environment:` block, next to `SKILL_RUNNER_URL`:

```yaml
      SKILL_RUNNER_NET_URL: http://skill-runner-net:9000
      EGRESS_PROXY_URL: egress-proxy:3128
      EGRESS_PROXY_CONTROL_URL: http://egress-proxy:3129
      EGRESS_PROXY_TOKEN: ${EGRESS_PROXY_TOKEN:?Set EGRESS_PROXY_TOKEN in .env}
```

2. Add `- sandbox-net` to the `api` service's `networks:` list (it already has `backend` and `sandbox`).

3. Add both services immediately after `skill-runner`:

```yaml
  skill-runner-net:
    image: cyberguard-skill-runner:1.0.0-rc.1
    build:
      context: .
      dockerfile: skill-runner/Dockerfile
    environment:
      SKILL_RUNNER_TOKEN: ${SKILL_RUNNER_TOKEN:?Set SKILL_RUNNER_TOKEN in .env}
    # Same image as skill-runner; the only difference is which network it is on.
    # `sandbox-net` is internal, so the sole reachable endpoint is egress-proxy.
    networks:
      - sandbox-net
    tmpfs:
      - /tmp:uid=10001,gid=10001,mode=1777,size=64m
    pids_limit: 128
    mem_limit: 512m
    cpus: 1.0
    <<: *app-hardening
    restart: unless-stopped

  egress-proxy:
    image: cyberguard-egress-proxy:1.0.0-rc.1
    build:
      context: .
      dockerfile: egress-proxy/Dockerfile
    command: ["python", "-m", "egress_proxy.main"]
    environment:
      EGRESS_PROXY_TOKEN: ${EGRESS_PROXY_TOKEN:?Set EGRESS_PROXY_TOKEN in .env}
    # The only service bridging the sandbox to the outside. Not on `backend`,
    # so a rebinding trick that slipped the IP check still reaches no database.
    networks:
      - sandbox-net
      - egress
    pids_limit: 128
    mem_limit: 256m
    cpus: 0.5
    <<: *app-hardening
    restart: unless-stopped
```

4. Extend the `networks:` block at the bottom:

```yaml
networks:
  backend:
  # api reaches skill-runner here. Compose network membership is bidirectional,
  # so api:8000 stays reachable from a script — see the design's 5.3.1. What
  # this removes is postgres, redis, and all egress.
  sandbox:
    internal: true
  # Phase 2: the allowlist runner and the proxy. Internal for the same reason —
  # the only way out of it is through egress-proxy, which checks every hop.
  sandbox-net:
    internal: true
  # Ordinary network. egress-proxy alone is attached to it.
  egress:
```

5. In `.env.example`, after `SKILL_RUNNER_TOKEN`:

```bash
# Control-plane token for the egress proxy. Held by api and the proxy only —
# never by a runner, which is what keeps a script from granting itself egress.
EGRESS_PROXY_TOKEN=replace-with-another-long-random-token
```

- [ ] **Step 4: Run tests and validate the stack**

Run: `.venv/bin/python -m pytest tests/test_invariants_static.py -k "inv40 or inv41" -v`
Expected: all pass (INV-40 unchanged, INV-41 now passing)

Run: `POSTGRES_PASSWORD=x REDIS_PASSWORD=x ENCRYPTION_KEY=x SECRET_KEY=x RUNNER_TOKEN=x SKILL_RUNNER_TOKEN=y EGRESS_PROXY_TOKEN=z BOOTSTRAP_ADMIN_PASSWORD=x docker compose config --quiet && echo COMPOSE_OK`
Expected: `COMPOSE_OK`

Run: `docker build -f egress-proxy/Dockerfile -t cyberguard-egress-proxy:verify . && docker run --rm -e EGRESS_PROXY_TOKEN=t cyberguard-egress-proxy:verify python -c "import egress_proxy.main as m; print('ok', sorted(m.ALLOWED_PORTS), m.__doc__.splitlines()[0])"`
Expected: `ok [80, 443] Forward proxy for sandboxed skill scripts.`

- [ ] **Step 5: Commit**

```bash
git add egress-proxy/ docker-compose.yml .env.example tests/test_invariants_static.py
git commit -m "feat: add the egress proxy container and sandbox-net segment

INV-41: skill-runner-net has no route of its own, egress-proxy is the
only service bridging sandbox-net to the outside, phase 1's skill-runner
is unchanged, and no runner receives the control token."
```

---

### Task 6: The runner accepts a proxy URL

**Files:**
- Modify: `skill_runner/main.py`
- Test: `tests/test_skill_runner_endpoints.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `/run` accepts an optional `proxy_url: str`; when present the child environment gains `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, `https_proxy` and nothing else

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skill_runner_endpoints.py`, inside `class TestSkillRunner`:

```python
    def test_proxy_url_reaches_the_child_environment(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20,
                      proxy_url="http://nonce123:x@egress-proxy:3128", files=[
            _f("scripts/x.py",
               "import os\n"
               "print(os.environ.get('HTTP_PROXY'), os.environ.get('https_proxy'))\n"),
        ])
        self.assertEqual(r.json()["stdout"].strip(),
                         "http://nonce123:x@egress-proxy:3128 "
                         "http://nonce123:x@egress-proxy:3128")

    def test_proxy_url_adds_nothing_else_to_the_environment(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20,
                      proxy_url="http://nonce123:x@egress-proxy:3128", files=[
            _f("scripts/x.py",
               "import os; print(sorted(k for k in os.environ))"),
        ])
        seen = set(eval(r.json()["stdout"].strip()))
        self.assertEqual(
            seen,
            {"PATH", "LANG", "PYTHONDONTWRITEBYTECODE", "HOME", "TMPDIR",
             "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"})

    def test_without_a_proxy_url_the_child_has_no_proxy_variables(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py",
               "import os; print([k for k in os.environ if 'PROXY' in k.upper()])"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "[]")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_skill_runner_endpoints.py -k proxy -v`
Expected: FAIL — the child prints `None None`

- [ ] **Step 3: Write minimal implementation**

In `skill_runner/main.py`, inside `run()`, replace the env construction:

```python
        env = dict(MINIMAL_ENV_BASE, HOME=scratch, TMPDIR=scratch)
```

with:

```python
        env = dict(MINIMAL_ENV_BASE, HOME=scratch, TMPDIR=scratch)
        # Phase 2: per-execution egress. The URL carries the nonce as proxy
        # credentials, so an ordinary urllib call is scoped without the script
        # author doing anything. It is a convenience, not the boundary — the
        # boundary is that this container has no other route out.
        proxy_url = body.get("proxy_url")
        if proxy_url:
            env.update({
                "HTTP_PROXY": proxy_url, "HTTPS_PROXY": proxy_url,
                "http_proxy": proxy_url, "https_proxy": proxy_url,
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_skill_runner_endpoints.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add skill_runner/main.py tests/test_skill_runner_endpoints.py
git commit -m "feat: let the runner inject a per-execution proxy URL"
```

---

### Task 7: Executor grant/run/revoke

**Files:**
- Modify: `app/services/tool_executor.py`
- Test: `tests/test_skill_script_egress.py`

**Interfaces:**
- Consumes: Task 4's control protocol; Task 6's `proxy_url`
- Produces:
  - Module constants `SKILL_RUNNER_NET_URL`, `EGRESS_PROXY_URL`, `EGRESS_PROXY_CONTROL_URL`, `EGRESS_PROXY_TOKEN`, `GRANT_TTL_MARGIN_SECONDS = 30`
  - `async _grant_egress(nonce: str, allowlist: list[str], ttl: float) -> None` — raises on failure
  - `async _revoke_egress(nonce: str) -> None` — never raises
  - `_execute_skill_script` branches on `tool.script_network`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_script_egress.py`:

```python
"""Allowlist executions grant before dispatch and revoke afterwards."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.tool_executor as te


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"stdout": "ok", "stderr": "", "exit_code": 0,
                                    "duration_ms": 5, "timed_out": False}
        self.text = "ok"

    def json(self):
        return self._payload


class _Client:
    calls: list = []
    run_status: int = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.calls.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/run"):
            return _Resp(status_code=_Client.run_status)
        return _Resp(payload={"ok": True})


def _tool(**over):
    base = dict(
        name="triage", source_skill_id=7, source_script_path="scripts/x.py",
        source_bundle_digest=None, script_network="allowlist",
        script_network_allowlist=["vendor.example"],
        command_template="python3 scripts/x.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        timeout_seconds=30, action_category="observe", rollback_command_template=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


FILES = [("scripts/x.py", b"print('ok')")]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _Client.calls = []
    _Client.run_status = 200
    monkeypatch.setattr(te.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(te, "SKILL_RUNNER_URL", "http://skill-runner:9000")
    monkeypatch.setattr(te, "SKILL_RUNNER_NET_URL", "http://skill-runner-net:9000")
    monkeypatch.setattr(te, "EGRESS_PROXY_URL", "egress-proxy:3128")
    monkeypatch.setattr(te, "EGRESS_PROXY_CONTROL_URL", "http://egress-proxy:3129")
    monkeypatch.setattr(te, "EGRESS_PROXY_TOKEN", "control-token")
    monkeypatch.setattr(te, "SKILL_RUNNER_TOKEN", "skill-token")

    async def _load(_skill_id):
        return FILES
    monkeypatch.setattr(te, "_load_bundle_for_tool", _load)


def _digest():
    from app.services import skill_bundle
    return skill_bundle.bundle_digest(FILES)


@pytest.mark.asyncio
async def test_allowlist_run_grants_dispatches_then_revokes():
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest=_digest()), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "completed"

    urls = [c["url"] for c in _Client.calls]
    assert urls == ["http://egress-proxy:3129/grant",
                    "http://skill-runner-net:9000/run",
                    "http://egress-proxy:3129/revoke"]

    grant, run, revoke = _Client.calls
    assert grant["headers"]["X-Egress-Token"] == "control-token"
    assert grant["json"]["allowlist"] == ["vendor.example"]
    assert grant["json"]["ttl"] == 30 + te.GRANT_TTL_MARGIN_SECONDS
    nonce = grant["json"]["nonce"]
    assert len(nonce) >= 32
    assert run["json"]["proxy_url"] == f"http://{nonce}:x@egress-proxy:3128"
    assert "X-Egress-Token" not in run["headers"]
    assert revoke["json"]["nonce"] == nonce


@pytest.mark.asyncio
async def test_revoke_happens_even_when_the_run_fails():
    _Client.run_status = 500
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest=_digest()), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert [c["url"] for c in _Client.calls][-1] == "http://egress-proxy:3129/revoke"


@pytest.mark.asyncio
async def test_a_none_tool_never_touches_the_proxy():
    result = await te._pool_execute(
        SimpleNamespace(
            tool=_tool(script_network="none", script_network_allowlist=None,
                       source_bundle_digest=_digest()),
            user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "completed"
    assert [c["url"] for c in _Client.calls] == ["http://skill-runner:9000/run"]


@pytest.mark.asyncio
async def test_allowlist_without_hosts_refuses_rather_than_running_unscoped():
    result = await te._pool_execute(
        SimpleNamespace(
            tool=_tool(script_network_allowlist=[], source_bundle_digest=_digest()),
            user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert "allowlist" in result["error"].lower()
    assert _Client.calls == []


@pytest.mark.asyncio
async def test_a_failed_grant_refuses_rather_than_running_without_network(monkeypatch):
    class _Failing(_Client):
        async def post(self, url, json=None, headers=None):
            _Client.calls.append({"url": url, "json": json, "headers": headers})
            if url.endswith("/grant"):
                raise RuntimeError("proxy unreachable")
            return _Resp()

    monkeypatch.setattr(te.httpx, "AsyncClient", _Failing)
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest=_digest()), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert "egress" in result["error"].lower()
    assert not any(c["url"].endswith("/run") for c in _Client.calls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_script_egress.py -v`
Expected: FAIL — `AttributeError: module 'app.services.tool_executor' has no attribute 'SKILL_RUNNER_NET_URL'`

- [ ] **Step 3: Write minimal implementation**

In `app/services/tool_executor.py`, extend the constants next to `SKILL_RUNNER_TOKEN`:

```python
SKILL_RUNNER_NET_URL = os.environ.get("SKILL_RUNNER_NET_URL", "http://skill-runner-net:9000")
EGRESS_PROXY_URL = os.environ.get("EGRESS_PROXY_URL", "egress-proxy:3128")
EGRESS_PROXY_CONTROL_URL = os.environ.get("EGRESS_PROXY_CONTROL_URL", "http://egress-proxy:3129")
EGRESS_PROXY_TOKEN = os.environ.get("EGRESS_PROXY_TOKEN", "")
# A grant must outlive its execution, but only just.
GRANT_TTL_MARGIN_SECONDS = 30
```

Add above `_execute_skill_script`:

```python
async def _grant_egress(nonce: str, allowlist: List[str], ttl: float) -> None:
    """Register one execution's allowlist with the proxy. Raises on failure."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{EGRESS_PROXY_CONTROL_URL}/grant",
            json={"nonce": nonce, "allowlist": list(allowlist), "ttl": ttl},
            headers={"X-Egress-Token": EGRESS_PROXY_TOKEN},
        )
    if r.status_code != 200:
        raise RuntimeError(f"egress grant refused: {r.status_code} {r.text[:200]}")


async def _revoke_egress(nonce: str) -> None:
    """Best-effort revoke. Grants also expire on their own TTL."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{EGRESS_PROXY_CONTROL_URL}/revoke",
                json={"nonce": nonce},
                headers={"X-Egress-Token": EGRESS_PROXY_TOKEN},
            )
    except Exception as e:  # noqa: BLE001 - revoke must not mask the run's result
        logging.getLogger(__name__).warning("egress revoke failed for %s: %s", nonce, e)
```

Add `import logging` to the module imports if it is not already there.

Then in `_execute_skill_script`, replace everything from `payload = {` through the `return {...}` at the end with:

```python
    payload = {
        "argv": argv,
        "timeout": timeout,
        "files": [
            {"path": path, "content_b64": base64.b64encode(content).decode()}
            for path, content in files
        ],
    }

    if (getattr(tool, "script_network", None) or "none") != "allowlist":
        return await _post_to_runner(SKILL_RUNNER_URL, payload, timeout)

    allowlist = list(getattr(tool, "script_network_allowlist", None) or [])
    if not allowlist:
        return {"status": "error", "is_error": True,
                "error": "tool requests allowlist networking but its allowlist is empty"}

    import secrets

    nonce = secrets.token_urlsafe(32)
    try:
        await _grant_egress(nonce, allowlist, timeout + GRANT_TTL_MARGIN_SECONDS)
    except Exception as e:
        # Never silently downgrade to "run it without network": the script was
        # approved on the understanding that it can reach those hosts.
        return {"status": "error", "is_error": True,
                "error": f"could not establish egress grant: {e}"}

    payload["proxy_url"] = f"http://{nonce}:x@{EGRESS_PROXY_URL}"
    try:
        return await _post_to_runner(SKILL_RUNNER_NET_URL, payload, timeout)
    finally:
        await _revoke_egress(nonce)
```

and add the shared POST helper just above `_execute_skill_script`:

```python
async def _post_to_runner(base_url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """POST a run to a skill runner and normalize its reply."""
    try:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            r = await client.post(
                f"{base_url}/run", json=payload,
                headers={"X-Skill-Runner-Token": SKILL_RUNNER_TOKEN},
            )
    except Exception as e:
        return {"status": "error", "is_error": True, "error": f"skill-runner unreachable: {e}"}

    if r.status_code != 200:
        return {"status": "error", "is_error": True,
                "error": f"skill-runner {r.status_code}: {r.text[:200]}"}

    data = r.json()
    exit_code = data.get("exit_code")
    timed_out = data.get("timed_out", False)
    is_error = bool(timed_out) or (exit_code not in (0, None))
    return {
        "status": "error" if is_error else "completed",
        "stdout": _truncate(data.get("stdout", "")),
        "stderr": _truncate(data.get("stderr", "")),
        "exit_code": exit_code,
        "duration_ms": data.get("duration_ms"),
        "timed_out": timed_out,
        "is_error": is_error,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_skill_script_egress.py tests/test_skill_script_execution.py tests/test_tool_executor.py -v`
Expected: 5 + 3 + existing passed

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_skill_script_egress.py
git commit -m "feat: grant and revoke per-execution egress around a run

A failed grant refuses the execution rather than downgrading to a run
with no network — the script was approved on the understanding that it
can reach those hosts."
```

---

### Task 8: Promotion accepts an allowlist

**Files:**
- Modify: `app/schemas/skill.py`, `app/routers/skills.py`
- Test: `tests/test_skill_script_promotion.py`

**Interfaces:**
- Consumes: `validate_promotion` from Phase 1
- Produces: `SkillScriptPromoteRequest.script_network_allowlist: Optional[List[str]]`; `validate_promotion` accepts `script_network="allowlist"` with a validated list

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skill_script_promotion.py`:

```python
@pytest.mark.asyncio
async def test_allowlist_networking_is_accepted_with_hosts():
    data = await validate_promotion(
        _DB(BUNDLE), 1, "scripts/triage.py",
        _body(script_network="allowlist",
              script_network_allowlist=["vendor.example", ".api.vendor.example"]))
    assert data["script_network"] == "allowlist"
    assert data["script_network_allowlist"] == ["vendor.example", ".api.vendor.example"]


@pytest.mark.asyncio
async def test_allowlist_networking_requires_at_least_one_host():
    with pytest.raises(HTTPException, match="at least one host"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(script_network="allowlist",
                                       script_network_allowlist=[]))


@pytest.mark.asyncio
async def test_allowlist_rejects_a_bare_ip_address():
    # A literal address sidesteps the whole point of naming a destination.
    with pytest.raises(HTTPException, match="hostname"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(script_network="allowlist",
                                       script_network_allowlist=["93.184.216.34"]))


@pytest.mark.asyncio
async def test_allowlist_rejects_wildcards_other_than_a_leading_dot():
    with pytest.raises(HTTPException, match="hostname"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(script_network="allowlist",
                                       script_network_allowlist=["*.vendor.example"]))


@pytest.mark.asyncio
async def test_allowlist_is_ignored_for_none_networking():
    data = await validate_promotion(
        _DB(BUNDLE), 1, "scripts/triage.py",
        _body(script_network="none", script_network_allowlist=["vendor.example"]))
    assert data["script_network_allowlist"] is None


@pytest.mark.asyncio
async def test_unknown_network_mode_is_rejected():
    with pytest.raises(HTTPException, match="script_network"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(script_network="everything"))
```

Also update `_body` in that file to carry the new field:

```python
def _body(**over):
    base = dict(
        name="triage-script", description="triage an alert",
        command_template="python3 scripts/triage.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        required_permission=None, action_category="observe", risk_tier="low",
        permission_level="medium", timeout_seconds=60, script_network="none",
        script_network_allowlist=None,
    )
    base.update(over)
    return SkillScriptPromoteRequest(**base)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_skill_script_promotion.py -v`
Expected: FAIL — `SkillScriptPromoteRequest` rejects the unexpected field / `allowlist` still refused

- [ ] **Step 3: Write minimal implementation**

In `app/schemas/skill.py`, add to `SkillScriptPromoteRequest`:

```python
    script_network_allowlist: Optional[List[str]] = None
```

In `app/routers/skills.py`, add next to the other module constants:

```python
SCRIPT_NETWORK_MODES = ("none", "allowlist")
_HOSTNAME_RE = re.compile(
    r"^\.?(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")
```

and `import ipaddress` plus `import re` at the top of the file.

Add the helper above `validate_promotion`:

```python
def _validated_allowlist(entries) -> list[str]:
    """Check egress allowlist entries at review time, not at first request."""
    cleaned: list[str] = []
    for raw in entries or []:
        host = str(raw or "").strip().lower().rstrip(".")
        if not host:
            continue
        probe = host[1:] if host.startswith(".") else host
        try:
            ipaddress.ip_address(probe)
        except ValueError:
            pass
        else:
            raise HTTPException(
                status_code=400,
                detail=f"allowlist entry {raw!r} is an IP address; name a hostname so "
                       "the destination is reviewable")
        if not _HOSTNAME_RE.match(host):
            raise HTTPException(
                status_code=400,
                detail=f"allowlist entry {raw!r} is not a hostname; use example.com "
                       "for one host or .example.com for its subdomains")
        cleaned.append(host)
    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="allowlist networking needs at least one host")
    return cleaned
```

In `validate_promotion`, replace the Phase 1 rejection block:

```python
    if body.script_network != "none":
        raise HTTPException(
            status_code=400,
            detail=f"script_network={body.script_network!r} is not supported yet; "
                   "only 'none' is available in this phase",
        )
```

with:

```python
    if body.script_network not in SCRIPT_NETWORK_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"script_network must be one of {', '.join(SCRIPT_NETWORK_MODES)}")
    allowlist = (
        _validated_allowlist(body.script_network_allowlist)
        if body.script_network == "allowlist" else None
    )
```

and change the returned dict's last field from `"script_network_allowlist": None` to `"script_network_allowlist": allowlist`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_skill_script_promotion.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add app/schemas/skill.py app/routers/skills.py tests/test_skill_script_promotion.py
git commit -m "feat: accept a validated egress allowlist at promotion"
```

---

### Task 9: Promotion UI, docs, and full verification

**Files:**
- Modify: `webui/src/pages/Skills.tsx`, `webui/src/i18n/en.json`, `webui/src/i18n/zh.json`
- Modify: `docs/delivery/ARCHITECTURE_AND_SECURITY.md`, `README.md`

**Interfaces:**
- Consumes: Task 8's schema field

- [ ] **Step 1: Add the i18n keys**

In `webui/src/i18n/en.json`, inside `skills`:

```json
    "promoteNetwork": "Network",
    "promoteNetworkNone": "No network",
    "promoteNetworkAllowlist": "Allowlisted hosts only",
    "promoteAllowlist": "Allowed hosts (one per line)",
    "promoteAllowlistHint": "example.com for one host, .example.com for its subdomains. Ports 80 and 443 only. A host that resolves to a private or metadata address is refused at request time."
```

In `webui/src/i18n/zh.json`, inside `skills`:

```json
    "promoteNetwork": "网络",
    "promoteNetworkNone": "无网络",
    "promoteNetworkAllowlist": "仅白名单主机",
    "promoteAllowlist": "允许的主机（每行一个）",
    "promoteAllowlistHint": "example.com 精确匹配单个主机，.example.com 匹配其子域。仅开放 80 和 443 端口。解析到私有地址或元数据地址的主机会在请求时被拒绝。"
```

- [ ] **Step 2: Add the controls to the promotion modal**

In `webui/src/pages/Skills.tsx`, add to the `PromoteForm` interface and `EMPTY_PROMOTE_FORM`:

```typescript
  script_network_allowlist: string
```

```typescript
  script_network: 'none', script_network_allowlist: '',
```

Replace this line in the modal, which states the network posture:

```tsx
              {t('skills.promoteReview')} {t('skills.promoteNoNetwork')}
```

with one that only states the review instruction, since the posture is now chosen:

```tsx
              {t('skills.promoteReview')}
```

Then, inside the `<div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>` block, after the RISK TIER field, add:

```tsx
                  <div>
                    <label className="form-label">{t('skills.promoteNetwork').toUpperCase()}</label>
                    <select className="form-input" value={promoteForm.script_network}
                      onChange={e => setPromoteForm(f => ({ ...f, script_network: e.target.value }))}>
                      <option value="none">{t('skills.promoteNetworkNone')}</option>
                      <option value="allowlist">{t('skills.promoteNetworkAllowlist')}</option>
                    </select>
                  </div>
                  {promoteForm.script_network === 'allowlist' && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label className="form-label">{t('skills.promoteAllowlist').toUpperCase()}</label>
                      <textarea className="form-input" rows={3}
                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                        value={promoteForm.script_network_allowlist}
                        placeholder={'vendor.example\n.api.vendor.example'}
                        onChange={e => setPromoteForm(f => ({
                          ...f, script_network_allowlist: e.target.value }))} />
                      <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4, lineHeight: 1.6 }}>
                        {t('skills.promoteAllowlistHint')}
                      </div>
                    </div>
                  )}
```

In `submitPromotion`, convert the textarea to a list:

```typescript
      await api.promoteSkillScript(Number(promoteSkill.id), promoteScript, {
        ...promoteForm,
        required_permission: promoteForm.required_permission || null,
        input_schema_json: promoteForm.input_schema_json || null,
        script_network_allowlist: promoteForm.script_network === 'allowlist'
          ? promoteForm.script_network_allowlist.split('\n').map(s => s.trim()).filter(Boolean)
          : null,
      })
```

- [ ] **Step 3: Update the documentation**

In `docs/delivery/ARCHITECTURE_AND_SECURITY.md`, replace the paragraph beginning "Scripts execute in `skill-runner`, a separate container on an `internal: true` network" with:

```markdown
Scripts execute in a runner on an `internal: true` network: `python3`/`sh` and
the standard library only, and a subprocess environment carrying no token or
secret. The bundle is written to tmpfs per execution and deleted afterwards; the
bundle tree is read-only and a separate scratch directory is the only writable
place, so a script cannot rewrite the code its approval covered.

A script approved with no network runs in `skill-runner`, which has no route off
its segment at all. A script approved with an egress allowlist runs in
`skill-runner-net`, whose only reachable endpoint is `egress-proxy` — the sole
service bridging that segment to the internet. Before each such run the API
registers a one-execution nonce with the proxy carrying that tool's allowlist,
and the nonce travels to the script as proxy credentials; the proxy authorizes
every request by nonce, port, hostname and **resolved IP**, then connects to the
address it just validated. `HTTP_PROXY` is a convenience for well-behaved
clients, never the control: a script that ignores it finds no route.

`api:8000` remains reachable from the sandbox segments — compose network
membership is bidirectional and plain compose cannot express a one-way rule —
but a script holds no credential for it, so its reach there is the
unauthenticated surface. This is a known limit, recorded rather than left to be
discovered.
```

In `README.md`, extend the required-values sentence to include `EGRESS_PROXY_TOKEN`:

```markdown
`RUNNER_TOKEN`, `SKILL_RUNNER_TOKEN`, `EGRESS_PROXY_TOKEN`, and
`BOOTSTRAP_ADMIN_PASSWORD` values. `SKILL_RUNNER_TOKEN` and `EGRESS_PROXY_TOKEN`
must each differ from `RUNNER_TOKEN` and from one another — keeping them separate
is what bounds what a sandboxed script can reach. Generate the two
```

- [ ] **Step 4: Run every gate**

Run: `make check`
Expected: Python suite green (703 from Phase 1 plus this plan's additions), tsc app + test, eslint at baseline, npm audit clean, vitest passing

Run: `POSTGRES_PASSWORD=x REDIS_PASSWORD=x ENCRYPTION_KEY=x SECRET_KEY=x RUNNER_TOKEN=x SKILL_RUNNER_TOKEN=y EGRESS_PROXY_TOKEN=z BOOTSTRAP_ADMIN_PASSWORD=x docker compose config --quiet && echo COMPOSE_OK`
Expected: `COMPOSE_OK`

- [ ] **Step 5: Commit**

```bash
git add webui/src/pages/Skills.tsx webui/src/i18n/en.json webui/src/i18n/zh.json \
        docs/delivery/ARCHITECTURE_AND_SECURITY.md README.md
git commit -m "feat: choose an egress allowlist when promoting a script

The approver names the hosts while looking at the code that will call
them, which is the only moment the two can be judged together."
```

---

## Deferred

Letting the model write a script during a chat and run it is a separate project. Two findings from investigating it are recorded in §10 of the spec: no code-execution path exists today, and tool-level approvals have no resume loop (`_request_approval` writes records that `graph_resume_target` returns `None` for). The second is the real cost of that feature and should be scoped on its own.
