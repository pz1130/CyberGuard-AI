"""Webhook configuration model — bi-directional.

  direction="incoming" : external service POSTs to /api/v1/webhooks/incoming/{token}
                         → payload is dispatched to the Master Agent.
  direction="outgoing" : CyberGuard fires an HTTP POST to outgoing_url whenever
                         a subscribed event occurs (e.g. approval.required).
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, CheckConstraint,
)
from app.core.database import Base


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    direction = Column(String(16), nullable=False)  # "incoming" | "outgoing"
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # --- Incoming-only -----------------------------------------------------
    # SHA-256 hash of the public token (plaintext shown only at creation /
    # regeneration). Caller hits /api/v1/webhooks/incoming/<plaintext>;
    # lookup is by hash.
    incoming_token_hash = Column(String(128), nullable=True, index=True)

    # --- Outgoing-only -----------------------------------------------------
    outgoing_url = Column(String(1024), nullable=True)
    # Optional HMAC-SHA256 secret (AES-256 encrypted). When set, requests
    # carry X-CyberGuard-Signature: sha256=<hex>.
    outgoing_secret_encrypted = Column(Text, nullable=True)
    # List of subscribed event names, e.g. ["approval.required"]
    outgoing_events = Column(JSON, nullable=True)

    # --- Stats / observability --------------------------------------------
    last_triggered_at = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('incoming', 'outgoing')",
            name="ck_webhooks_direction",
        ),
        # Direction-specific fields must be present for that direction.
        CheckConstraint(
            "(direction = 'outgoing' AND outgoing_url IS NOT NULL) "
            "OR (direction = 'incoming' AND incoming_token_hash IS NOT NULL)",
            name="ck_webhooks_direction_fields",
        ),
    )

    def __repr__(self):
        return f"<Webhook {self.id} {self.name} [{self.direction}]>"
