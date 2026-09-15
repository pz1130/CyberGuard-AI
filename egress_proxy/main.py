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
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
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
