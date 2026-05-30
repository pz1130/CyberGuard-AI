"""Webhook service: event emission + HMAC-signed outgoing delivery.

Public API:
  emit(event, payload)       — Called from anywhere; fans out to all active
                               outgoing webhooks subscribed to `event`. Queues
                               a Celery task per webhook so callers never block.
  deliver_sync(webhook, event, payload)
                             — Synchronous HTTP delivery used by the Celery
                               task and by the WebUI test-fire endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, get_sync_session
from app.core.security import decrypt_data
from app.models.webhook import Webhook
from app.schemas.webhook import SUPPORTED_EVENTS

logger = logging.getLogger(__name__)

# SSRF protection — block private/metadata addresses.
_BLOCKED_HOSTS = frozenset({
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.azure.com",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
})
_PRIVATE_PREFIXES = (
    "10.", "192.168.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
    "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
)


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed scheme '{parsed.scheme}'")
    host = parsed.hostname or ""
    if host in _BLOCKED_HOSTS or host.startswith(_PRIVATE_PREFIXES):
        raise ValueError(f"Disallowed host (private/metadata): {host}")


def _sign(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


# ---------------------------------------------------------------------------
# Outgoing delivery
# ---------------------------------------------------------------------------

def deliver_sync(
    *,
    webhook_id: int,
    event: str,
    payload: Dict[str, Any],
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Synchronously POST to a single outgoing webhook. Updates DB counters.

    Returns {success, status_code, latency_ms, error}. Never raises — all
    failures recorded in the webhook row.

    Called from:
      - app.workers.tasks.deliver_webhook_task (Celery, with retries)
      - app.routers.webhooks /test endpoint (one-shot, no retry)
    """
    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        result = session.execute(select(Webhook).where(Webhook.id == webhook_id))
        wh = result.scalar_one_or_none()
        if not wh or wh.direction != "outgoing":
            return {"success": False, "status_code": None, "latency_ms": 0,
                    "error": f"Webhook {webhook_id} not an active outgoing webhook"}

        if not wh.is_active:
            return {"success": False, "status_code": None, "latency_ms": 0,
                    "error": "Webhook is disabled"}

        try:
            _validate_url(wh.outgoing_url or "")
        except ValueError as e:
            wh.failure_count += 1
            wh.last_error = str(e)
            session.commit()
            return {"success": False, "status_code": None, "latency_ms": 0,
                    "error": str(e)}

        secret_plain: Optional[str] = None
        if wh.outgoing_secret_encrypted:
            try:
                secret_plain = decrypt_data(wh.outgoing_secret_encrypted)
            except Exception as e:
                logger.warning("[webhook %s] secret decrypt failed: %s", webhook_id, e)

        body_dict = {
            "event": event,
            "delivered_at": datetime.now(timezone.utc).isoformat() + "Z",
            "webhook_id": webhook_id,
            "data": payload,
        }
        body_bytes = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CyberGuard-Webhook/1.0",
            "X-CyberGuard-Event": event,
            "X-CyberGuard-Webhook-Id": str(webhook_id),
        }
        if secret_plain:
            headers["X-CyberGuard-Signature"] = _sign(secret_plain, body_bytes)

        wh.trigger_count += 1
        wh.last_triggered_at = datetime.now(timezone.utc)
        session.commit()  # commit the trigger before the HTTP call so reload sees it

        t0 = time.monotonic()
        try:
            verify_certs = urlparse(wh.outgoing_url).scheme == "https"
            with httpx.Client(timeout=timeout, verify=verify_certs) as client:
                resp = client.post(wh.outgoing_url, content=body_bytes, headers=headers)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            ok = 200 <= resp.status_code < 300
            # Reload to write counters atomically with status code.
            session.refresh(wh)
            if ok:
                wh.success_count += 1
                wh.last_error = None
            else:
                wh.failure_count += 1
                wh.last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            session.commit()
            return {"success": ok, "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "error": None if ok else wh.last_error}
        except Exception as e:
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            session.refresh(wh)
            wh.failure_count += 1
            wh.last_error = str(e)[:500]
            session.commit()
            return {"success": False, "status_code": None,
                    "latency_ms": latency_ms, "error": str(e)}


# ---------------------------------------------------------------------------
# Event emission (caller side)
# ---------------------------------------------------------------------------

async def emit(event: str, payload: Dict[str, Any]) -> int:
    """Fan out an event to all active outgoing webhooks subscribed to it.

    Queues a Celery task per match (non-blocking). Returns the number of
    webhooks that were enqueued. Unknown event names are logged and dropped.
    """
    if event not in SUPPORTED_EVENTS:
        logger.warning("[webhook.emit] unknown event '%s' — ignoring", event)
        return 0

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Webhook).where(
                    Webhook.direction == "outgoing",
                    Webhook.is_active == True,  # noqa: E712
                )
            )
            webhooks = result.scalars().all()
    except Exception as e:
        logger.warning("[webhook.emit] DB load failed: %s", e)
        return 0

    enqueued = 0
    for wh in webhooks:
        events = wh.outgoing_events or []
        if event not in events:
            continue
        try:
            # Lazy import to avoid circular import at module load time.
            from app.workers.tasks import deliver_webhook_task
            deliver_webhook_task.apply_async(args=[wh.id, event, payload])
            enqueued += 1
        except Exception as e:
            logger.warning("[webhook.emit] enqueue webhook %s failed: %s", wh.id, e)

    return enqueued
