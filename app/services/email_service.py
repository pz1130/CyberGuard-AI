"""Async email notification service.

Mailbox settings are persisted by /email/config. Legacy environment fallback:
    SMTP_HOST          — SMTP server hostname (default: localhost)
    SMTP_PORT          — SMTP port (default: 587)
    SMTP_USERNAME      — SMTP auth username (optional)
    SMTP_PASSWORD      — SMTP auth password (optional)
    SMTP_FROM_EMAIL    — From address (default: cyberguard@localhost)
    SMTP_USE_TLS       — Enable STARTTLS (default: true)
    SMTP_ADMIN_EMAIL   — Admin recipient for approval/system alerts
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _cfg(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default


def _is_email_configured() -> bool:
    """Return True only if SMTP is minimally configured."""
    host = _cfg("SMTP_HOST")
    return bool(host and host != "localhost" and _cfg("SMTP_FROM_EMAIL"))


def smtp_status() -> dict:
    """Operator-visible SMTP readiness. Never includes secrets."""
    host = _cfg("SMTP_HOST")
    from_addr = _cfg("SMTP_FROM_EMAIL")
    admin = _cfg("SMTP_ADMIN_EMAIL")
    if not host or host == "localhost":
        reason = "SMTP_HOST is unset or localhost — approval email is skipped"
    elif not from_addr:
        reason = "SMTP_FROM_EMAIL is unset — approval email is skipped"
    else:
        reason = "SMTP is configured"
    return {
        "configured": _is_email_configured(),
        "reason": reason,
        "admin_email_set": bool(admin),
    }


def _build_message(
    to: str,
    subject: str,
    body_html: str,
    body_text: str,
    from_addr: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    return msg


def _send_sync(to: str, subject: str, body_html: str, body_text: str, cfg: dict | None = None) -> bool:
    """Blocking SMTP delivery with STARTTLS, implicit TLS, or plain relay."""
    from app.services.email_config import legacy_config
    cfg = cfg or legacy_config()
    msg = _build_message(to, subject, body_html, body_text, cfg["from_email"])
    try:
        security = cfg["smtp_security"]
        context = ssl.create_default_context()
        if security == "ssl":
            connection = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=15, context=context)
        else:
            connection = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15)
        with connection as server:
            if security == "starttls":
                server.starttls(context=context)
            if cfg.get("smtp_username"):
                server.login(cfg["smtp_username"], cfg.get("smtp_password", ""))
            refused = server.sendmail(cfg["from_email"], [to], msg.as_bytes())
            return not bool(refused)
    except Exception as exc:
        logger.warning("[email] SMTP delivery failed (%s)", type(exc).__name__)
        return False


async def _send_oauth(to: str, subject: str, body_html: str, cfg: dict) -> bool:
    """Microsoft 365 app-only OAuth via Graph Mail.Send."""
    import httpx
    from urllib.parse import quote
    async with httpx.AsyncClient(timeout=15) as client:
        token = await client.post(
            f"https://login.microsoftonline.com/{cfg['oauth_tenant_id']}/oauth2/v2.0/token",
            data={"client_id": cfg["oauth_client_id"], "client_secret": cfg["oauth_client_secret"],
                  "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
        token.raise_for_status()
        response = await client.post(
            f"https://graph.microsoft.com/v1.0/users/{quote(cfg['from_email'], safe='')}/sendMail",
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            json={"message": {"subject": subject, "body": {"contentType": "HTML", "content": body_html},
                              "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": True})
        response.raise_for_status()
        return response.status_code == 202


async def send_email(to: str, subject: str, body_html: str,
                     body_text: Optional[str] = None, *, config: dict | None = None) -> bool:
    """Best-effort async delivery; never log credentials or token responses."""
    from app.services.email_config import load_email_config, config_status
    try:
        cfg = config if config is not None else await load_email_config()
        if not config_status(cfg)["configured"]:
            return False
        if cfg["method"] == "oauth":
            return await _send_oauth(to, subject, body_html, cfg)
        return await asyncio.to_thread(_send_sync, to, subject, body_html,
                                       body_text or _html_to_text(body_html), cfg)
    except Exception as exc:
        logger.warning("[email] Delivery failed (%s)", type(exc).__name__)
        return False


def _html_to_text(html: str) -> str:
    """Strip tags for plain-text fallback."""
    import re
    return re.sub(r"<[^>]+>", "", html).strip()


# ---------------------------------------------------------------------------
# Pre-built notification helpers
# ---------------------------------------------------------------------------

async def notify_approval_created(
    request_id: str,
    action_description: str,
    risk_level: str,
    user_id: int,
) -> None:
    """Notify admin that a new Human-in-the-Loop approval request is waiting."""
    from app.services.email_config import load_email_config, approval_recipients, config_status
    cfg = await load_email_config()
    if not cfg.get("notify_created", True) or not config_status(cfg)["configured"]:
        return
    recipients = await approval_recipients(cfg)
    from app.core.email_templates import render_notification
    subject, html = render_notification(cfg, "created", {
        "request_id": request_id, "action_description": action_description,
        "risk_level": risk_level.upper(), "user_id": user_id,
    })
    for recipient in recipients:
        await send_email(recipient, subject, html, config=cfg)


async def notify_approval_decided(
    to_email: str,
    request_id: str,
    decision: str,
    comment: Optional[str],
) -> None:
    """Notify the requester of an approval decision."""
    if not to_email:
        return
    from app.services.email_config import load_email_config
    cfg = await load_email_config()
    if not cfg.get("notify_decided", True):
        return
    from app.core.email_templates import render_notification
    subject, html = render_notification(cfg, "decided", {
        "request_id": request_id, "decision": decision.upper(), "comment": comment or "（无备注）",
    })
    await send_email(to_email, subject, html, config=cfg)
