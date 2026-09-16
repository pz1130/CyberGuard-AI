"""Manual audit export using RFC 5424 and RFC 6587 TCP framing."""
import asyncio
import json
import socket
from datetime import timezone

from app.schemas.audit import SyslogExportRequest


class SyslogExportError(Exception):
    def __init__(self, sent: int):
        self.sent = sent
        super().__init__("Syslog delivery failed")


def format_message(log, facility: int) -> bytes:
    timestamp = log.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    payload = {key: getattr(log, key) for key in (
        "id", "user_id", "agent_id", "action", "input_hash", "output_hash",
        "request_id", "prev_hash", "entry_hash", "chain_version",
    )}
    payload["timestamp"] = timestamp.isoformat()
    # JSON ASCII escaping also keeps control characters out of the wire message.
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return f"<{facility * 8 + 6}>1 {timestamp.isoformat()} - cyberguard - audit - {body}".encode("ascii")


async def send_logs(logs, config: SyslogExportRequest) -> int:
    """Return locally sent records; Syslog has no application acknowledgement."""
    if not logs:
        return 0
    sent = 0
    writer = None
    sock = None
    try:
        # Bound the whole export, including DNS, connection and every write.
        async with asyncio.timeout(30):
            if config.protocol == "tcp":
                _, writer = await asyncio.open_connection(config.host, config.port)
            elif logs:
                loop = asyncio.get_running_loop()
                addresses = await loop.getaddrinfo(
                    config.host, config.port, type=socket.SOCK_DGRAM)
                family, kind, proto, _, address = addresses[0]
                sock = socket.socket(family, kind, proto)
                sock.setblocking(False)
                await loop.sock_connect(sock, address)
            for log in logs:
                message = format_message(log, config.facility)
                if writer is not None:
                    writer.write(str(len(message)).encode("ascii") + b" " + message)
                    await writer.drain()
                else:
                    if len(message) > 65507:
                        raise ValueError("Syslog message exceeds UDP datagram limit")
                    await asyncio.get_running_loop().sock_sendall(sock, message)
                sent += 1
    except (OSError, TimeoutError, ValueError) as exc:
        raise SyslogExportError(sent) from exc
    finally:
        if sock is not None:
            sock.close()
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except (OSError, TimeoutError):
                pass
    return sent
