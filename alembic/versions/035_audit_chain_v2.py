"""Add audit chain version for payload-integrity verification.

Revision ID: 035_audit_chain_v2
Revises: 034_focus_security_operations
Create Date: 2026-09-12
"""
from typing import Sequence, Union
import hashlib
import json

import sqlalchemy as sa
from alembic import op


revision: str = "035_audit_chain_v2"
down_revision: Union[str, None] = "034_focus_security_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("chain_version", sa.Integer(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, user_id, agent_id, agent_name, action, action_category,
               confidence, human_reviewer, rollback_possible, risk_tier,
               input_hash, output_hash, request_id, timestamp, ip_address,
               user_agent, request_path, metadata_json
        FROM audit_logs
        WHERE entry_hash IS NOT NULL
        ORDER BY id ASC
    """)).mappings().all()
    prev_hash = "0" * 64
    for row in rows:
        timestamp = row["timestamp"]
        if timestamp is not None:
            timestamp = timestamp.replace(tzinfo=None).isoformat()
        payload = {
            "user_id": row["user_id"],
            "agent_id": str(row["agent_id"]) if row["agent_id"] is not None else None,
            "agent_name": row["agent_name"],
            "action": row["action"],
            "action_category": row["action_category"],
            "confidence": row["confidence"],
            "human_reviewer": row["human_reviewer"],
            "rollback_possible": row["rollback_possible"],
            "risk_tier": row["risk_tier"],
            "input_hash": row["input_hash"],
            "output_hash": row["output_hash"],
            "request_id": row["request_id"],
            "timestamp": timestamp,
            "ip_address": row["ip_address"],
            "user_agent": row["user_agent"],
            "request_path": row["request_path"],
            "metadata_json": row["metadata_json"],
            "chain_version": 2,
            "prev_hash": prev_hash,
        }
        entry_hash = hashlib.sha256(
            (json.dumps(payload, sort_keys=True, default=str) + prev_hash).encode()
        ).hexdigest()
        bind.execute(
            sa.text("""
                UPDATE audit_logs
                SET prev_hash = :prev_hash, entry_hash = :entry_hash, chain_version = 2
                WHERE id = :id
            """),
            {"id": row["id"], "prev_hash": prev_hash, "entry_hash": entry_hash},
        )
        prev_hash = entry_hash


def downgrade() -> None:
    op.drop_column("audit_logs", "chain_version")
