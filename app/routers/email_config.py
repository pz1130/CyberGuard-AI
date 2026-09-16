"""Admin mailbox configuration and explicit test delivery."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.core.security import CredentialField, encrypt_data
from app.models.email_config import EmailConfig
from app.schemas.email_config import EmailConfigWrite, EmailTestRequest
from app.services.email_config import legacy_config, row_config, public_config

router = APIRouter()


@router.get("/email/config")
async def get_email_config(db: AsyncSession = Depends(get_db),
                           _=Depends(require_permission(Permission.SETTINGS_READ))):
    row = await db.get(EmailConfig, 1)
    return row_config(row) if row else public_config(legacy_config())


@router.put("/email/config")
async def save_email_config(body: EmailConfigWrite, db: AsyncSession = Depends(get_db),
                            actor: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE))):
    row = await db.get(EmailConfig, 1)
    if row is None:
        row = EmailConfig(id=1)
        db.add(row)
        # Preserve environment credentials on the first save if left blank.
        legacy = legacy_config()
        if legacy.get("smtp_password"):
            row.smtp_password_encrypted = encrypt_data(legacy["smtp_password"], CredentialField.EMAIL_SMTP_PASSWORD)
    # None keeps the saved secret; an empty string clears it.
    if body.smtp_password is not None:
        row.smtp_password_encrypted = (
            encrypt_data(body.smtp_password, CredentialField.EMAIL_SMTP_PASSWORD) if body.smtp_password else None)
    if body.oauth_client_secret is not None:
        row.oauth_client_secret_encrypted = (
            encrypt_data(body.oauth_client_secret, CredentialField.EMAIL_OAUTH_SECRET) if body.oauth_client_secret else None)
    if body.enabled and body.method == "oauth" and not row.oauth_client_secret_encrypted:
        raise HTTPException(422, "Microsoft client secret is required")
    if body.enabled and body.method == "smtp" and body.smtp_username and not row.smtp_password_encrypted:
        raise HTTPException(422, "SMTP password is required when a username is supplied")
    row.enabled = body.enabled
    row.config_json = body.model_dump(mode="json", exclude={"enabled", "smtp_password", "oauth_client_secret"})
    await db.commit()
    from app.core.audit import record_action
    await record_action(user_id=actor.user_id, action="email.config.update", risk_tier="medium",
                        input_data={"method": body.method, "enabled": body.enabled},
                        output_data={"saved": True})
    return row_config(row)


@router.post("/email/test")
async def test_email(body: EmailTestRequest,
                     _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    from app.services.email_service import send_email
    from app.services.email_config import load_email_config
    cfg = await load_email_config()
    if body.template == "connection":
        subject, html = "[CyberGuard] 邮箱配置测试", "<p>CyberGuard 邮件通知配置测试成功。</p>"
    else:
        from app.core.email_templates import render_notification, SAMPLE_VALUES
        subject, html = render_notification(cfg, body.template, SAMPLE_VALUES[body.template])
    sent = await send_email(body.to_email, subject, html, config=cfg)
    if not sent:
        raise HTTPException(502, "Email delivery failed. Check mailbox configuration, credentials and network access.")
    return {"sent": True}
