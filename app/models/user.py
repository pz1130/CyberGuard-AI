"""User and RBAC database models."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.time import utc_now


class User(Base):
    """User model with role-based access control."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    # Nullable: SSO-provisioned users have no local password.
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="viewer")
    is_active = Column(Boolean, default=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    # Identity provider for this account: "local" or "azure_ad".
    auth_provider = Column(String(50), nullable=False, default="local")
    # Stable external identity (Azure AD object id / "oid") for SSO accounts.
    external_id = Column(String(255), nullable=True, index=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    audit_logs = relationship("AuditLog", back_populates="user")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class RoleModel(Base):
    """Role model with permissions JSON."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    permissions_json = Column(Text, nullable=True)  # JSON array of permissions
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<RoleModel {self.name}>"
