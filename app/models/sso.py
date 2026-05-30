"""SSO (Azure AD / Entra ID) configuration models.

The client secret is intentionally NOT stored here — it is resolved from
a DB EnvVar record (``secret_env_var_id``) so the UI can manage it like
any other encrypted environment variable.  Only non-secret configuration
lives in the DB row.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from app.core.database import Base


class SsoConfig(Base):
    """Single-row (id=1) Azure AD SSO configuration."""

    __tablename__ = "sso_config"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=False, nullable=False)
    tenant_id = Column(String(255), nullable=True)
    client_id = Column(String(255), nullable=True)
    redirect_uri = Column(String(512), nullable=True)
    default_role = Column(String(50), default="viewer", nullable=False)
    allow_jit = Column(Boolean, default=True, nullable=False)
    # FK to env_vars.id — stores which DB EnvVar holds the Azure client secret
    secret_env_var_id = Column(Integer, ForeignKey("env_vars.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SsoRoleMapping(Base):
    """Maps an Azure AD group object-id or app-role value to an app role.

    Highest ``priority`` wins when a user matches multiple mappings.
    """

    __tablename__ = "sso_role_mapping"

    id = Column(Integer, primary_key=True, index=True)
    azure_key = Column(String(255), unique=True, nullable=False, index=True)
    app_role = Column(String(50), nullable=False)
    priority = Column(Integer, default=10, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
