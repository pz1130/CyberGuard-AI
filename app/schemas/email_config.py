"""Mailbox settings shared by the admin UI and notification sender."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator, field_validator, ValidationInfo
from app.core.email_templates import DEFAULT_TEMPLATES, validate_template
from app.schemas.email import InternalEmailStr


class EmailConfigWrite(BaseModel):
    enabled: bool = False
    method: Literal["smtp", "oauth"] = "smtp"
    from_email: InternalEmailStr | None = None
    admin_email: InternalEmailStr | None = None
    smtp_host: str = Field(default="", max_length=253, pattern=r"^[^\s/@?#]*$")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = Field(default="", max_length=255)
    smtp_password: str | None = Field(default=None, max_length=4096)
    oauth_tenant_id: UUID | None = None
    oauth_client_id: UUID | None = None
    oauth_client_secret: str | None = Field(default=None, max_length=4096)
    notify_created: bool = True
    notify_decided: bool = True

    created_subject: str = Field(default=DEFAULT_TEMPLATES["created_subject"], min_length=1, max_length=255)
    created_body: str = Field(default=DEFAULT_TEMPLATES["created_body"], min_length=1, max_length=50000)
    decided_subject: str = Field(default=DEFAULT_TEMPLATES["decided_subject"], min_length=1, max_length=255)
    decided_body: str = Field(default=DEFAULT_TEMPLATES["decided_body"], min_length=1, max_length=50000)

    @field_validator("created_subject", "created_body", "decided_subject", "decided_body")
    @classmethod
    def validate_mail_template(cls, value: str, info: ValidationInfo) -> str:
        kind, field = info.field_name.split("_")
        return validate_template(value, kind, subject=field == "subject")

    @model_validator(mode="after")
    def validate_enabled(self):
        if self.enabled:
            if not self.from_email:
                raise ValueError("A sender mailbox is required")
            if self.method == "smtp" and not self.smtp_host:
                raise ValueError("SMTP host is required")
            if self.method == "oauth" and not (self.oauth_tenant_id and self.oauth_client_id):
                raise ValueError("Microsoft tenant ID and client ID are required")
        return self


class EmailTestRequest(BaseModel):
    to_email: InternalEmailStr
    template: Literal["connection", "created", "decided"] = "connection"
