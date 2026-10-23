"""Load saved mailbox configuration, falling back to legacy SMTP environment."""
import os
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import CredentialField, decrypt_data
from app.models.email_config import EmailConfig
from app.core.email_templates import DEFAULT_TEMPLATES


def legacy_config() -> dict:
    host = os.getenv("SMTP_HOST", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "")
    return {
        **DEFAULT_TEMPLATES, "template_defaults": DEFAULT_TEMPLATES,
        "enabled": bool(host and host != "localhost" and sender),
        "method": "smtp", "from_email": sender or None,
        "admin_email": os.getenv("SMTP_ADMIN_EMAIL") or None,
        "smtp_host": host, "smtp_port": int(os.getenv("SMTP_PORT") or "587"),
        "smtp_security": "none" if os.getenv("SMTP_USE_TLS", "true").lower() in ("false", "0", "no") else "starttls",
        "smtp_username": os.getenv("SMTP_USERNAME", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "oauth_tenant_id": None, "oauth_client_id": None, "oauth_client_secret": "",
        "notify_created": True, "notify_decided": True, "source": "environment",
    }


def row_config(row: EmailConfig, *, secrets: bool = False) -> dict:
    cfg = {**DEFAULT_TEMPLATES, **row.config_json, "template_defaults": DEFAULT_TEMPLATES, "enabled": row.enabled, "source": "saved",
           "smtp_password_set": bool(row.smtp_password_encrypted),
           "oauth_client_secret_set": bool(row.oauth_client_secret_encrypted)}
    if secrets:
        cfg["smtp_password"] = decrypt_data(row.smtp_password_encrypted, CredentialField.EMAIL_SMTP_PASSWORD) if row.smtp_password_encrypted else ""
        cfg["oauth_client_secret"] = decrypt_data(row.oauth_client_secret_encrypted, CredentialField.EMAIL_OAUTH_SECRET) if row.oauth_client_secret_encrypted else ""
    return cfg


async def load_email_config() -> dict:
    async with AsyncSessionLocal() as db:
        row = await db.get(EmailConfig, 1)
        return row_config(row, secrets=True) if row else legacy_config()


def public_config(cfg: dict) -> dict:
    return {**{k: v for k, v in cfg.items() if k not in ("smtp_password", "oauth_client_secret")},
            "smtp_password_set": bool(cfg.get("smtp_password_set") or cfg.get("smtp_password")),
            "oauth_client_secret_set": bool(cfg.get("oauth_client_secret_set") or cfg.get("oauth_client_secret"))}


def config_status(cfg: dict) -> dict:
    ready = bool(cfg.get("enabled") and cfg.get("from_email"))
    if cfg.get("method") == "oauth":
        ready = ready and bool(cfg.get("oauth_tenant_id") and cfg.get("oauth_client_id") and
                               (cfg.get("oauth_client_secret") or cfg.get("oauth_client_secret_set")))
    else:
        ready = ready and bool(cfg.get("smtp_host"))
    return {"configured": ready, "reason": "Email is configured" if ready else "Email notifications are disabled or incomplete",
            "admin_email_set": bool(cfg.get("admin_email"))}


async def approval_recipients(cfg: dict) -> list[str]:
    from app.models.user import User
    from app.core.rbac import Role, Permission, has_permission
    roles = [role.value for role in Role if has_permission(role, Permission.APPROVAL_DECIDE)]
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.email).where(User.is_active.is_(True), User.role.in_(roles)))
        recipients = list(result.scalars().all())
    if cfg.get("admin_email"):
        recipients.append(cfg["admin_email"])
    return sorted(set(email for email in recipients if email))
