"""Global notification mailbox configuration; credentials are encrypted."""
from sqlalchemy import Boolean, Column, Integer, JSON, Text
from app.core.database import Base


class EmailConfig(Base):
    __tablename__ = "email_config"
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    config_json = Column(JSON, nullable=False, default=dict)
    smtp_password_encrypted = Column(Text, nullable=True)
    oauth_client_secret_encrypted = Column(Text, nullable=True)
