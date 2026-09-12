"""Async email notification service.

Configuration via environment variables:
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


def _send_sync(to: str, subject: str, body_html: str, body_text: str) -> bool:
    """Blocking SMTP send — called from asyncio.to_thread."""
    host = _cfg("SMTP_HOST", "localhost")
    port = int(_cfg("SMTP_PORT", "587"))
    username = _cfg("SMTP_USERNAME")
    password = _cfg("SMTP_PASSWORD")
    from_addr = _cfg("SMTP_FROM_EMAIL", "cyberguard@localhost")
    use_tls = _cfg("SMTP_USE_TLS", "true").lower() not in ("false", "0", "no")

    msg = _build_message(to, subject, body_html, body_text, from_addr)

    try:
        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=context)
                if username:
                    server.login(username, password)
                server.sendmail(from_addr, [to], msg.as_bytes())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                if username:
                    server.login(username, password)
                server.sendmail(from_addr, [to], msg.as_bytes())
        return True
    except Exception as e:
        logger.error(f"[email] Failed to send to {to!r}: {e}")
        return False


async def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
) -> bool:
    """Send an email asynchronously (non-blocking).

    Returns True on success, False on failure or when SMTP is not configured.
    Never raises — all errors are logged and swallowed.
    """
    if not _is_email_configured():
        logger.warning(
            "[email] SMTP not configured — skipping email to %r: %s (%s)",
            to, subject, smtp_status()["reason"],
        )
        return False
    plain = body_text or _html_to_text(body_html)
    return await asyncio.to_thread(_send_sync, to, subject, body_html, plain)


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
    admin_email = _cfg("SMTP_ADMIN_EMAIL")
    if not admin_email:
        return
    subject = f"[CyberGuard] 🔔 审批请求待处理 — 风险: {risk_level.upper()}"
    html = f"""
<h2>CyberGuard — 新审批请求</h2>
<table>
  <tr><th>请求 ID</th><td><code>{request_id}</code></td></tr>
  <tr><th>操作描述</th><td>{action_description}</td></tr>
  <tr><th>风险等级</th><td><strong>{risk_level.upper()}</strong></td></tr>
  <tr><th>发起用户 ID</th><td>{user_id}</td></tr>
</table>
<p>请登录 CyberGuard 管理界面处理此请求（有效期 1 小时）。</p>
"""
    await send_email(admin_email, subject, html)


async def notify_approval_decided(
    to_email: str,
    request_id: str,
    decision: str,
    comment: Optional[str],
) -> None:
    """Notify the requester of an approval decision."""
    if not to_email:
        return
    icon = "✅" if decision == "approved" else "❌"
    subject = f"[CyberGuard] {icon} 审批结果: {decision.upper()}"
    html = f"""
<h2>CyberGuard — 审批结果通知</h2>
<table>
  <tr><th>请求 ID</th><td><code>{request_id}</code></td></tr>
  <tr><th>决定</th><td><strong>{decision.upper()}</strong></td></tr>
  <tr><th>备注</th><td>{comment or '（无备注）'}</td></tr>
</table>
"""
    await send_email(to_email, subject, html)
