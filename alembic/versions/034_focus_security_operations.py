"""Retire untouched GRC defaults from the security-operations product.

Revision ID: 034_focus_security_operations
Revises: 033_drop_grc_assessments
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "034_focus_security_operations"
down_revision: Union[str, None] = "033_drop_grc_assessments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_SYSTEM_PROMPT = (
    "You are CyberGuard, a security operations assistant. You help users with "
    "threat analysis, vulnerability assessment, log analysis, and security "
    "compliance. Be precise and actionable."
)
NEW_SYSTEM_PROMPT = (
    "You are CyberGuard, a security operations assistant. You help users with "
    "threat analysis, vulnerability assessment, log analysis, and incident "
    "response. Be precise and actionable."
)
OLD_INTENT_PROMPT = """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Agent types: threat_intel, log_anomaly, vuln_scanner, remediation, compliance, osint, general
"""
NEW_INTENT_PROMPT = OLD_INTENT_PROMPT.replace(
    "remediation, compliance, osint", "remediation, osint"
)


def upgrade() -> None:
    # Exact-match updates preserve any administrator-customised configuration.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE master_agent_config SET system_prompt = :new "
            "WHERE system_prompt = :old"
        ),
        {"new": NEW_SYSTEM_PROMPT, "old": OLD_SYSTEM_PROMPT},
    )
    bind.execute(
        sa.text(
            "UPDATE master_agent_config SET intent_parser_prompt = :new "
            "WHERE intent_parser_prompt = :old"
        ),
        {"new": NEW_INTENT_PROMPT, "old": OLD_INTENT_PROMPT},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE master_agent_config SET system_prompt = :old "
            "WHERE system_prompt = :new"
        ),
        {"old": OLD_SYSTEM_PROMPT, "new": NEW_SYSTEM_PROMPT},
    )
    bind.execute(
        sa.text(
            "UPDATE master_agent_config SET intent_parser_prompt = :old "
            "WHERE intent_parser_prompt = :new"
        ),
        {"old": OLD_INTENT_PROMPT, "new": NEW_INTENT_PROMPT},
    )
