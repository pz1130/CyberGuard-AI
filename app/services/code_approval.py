"""Approval records for model-authored code.

The digest is what makes an approval mean something here. The graph re-runs its
executor node on resume, so the model is called again and may author different
code; without pinning the digest, an approval granted for reviewed code would
cover whatever the model produced the second time.

The record's ``request_id`` is derived from ``(run, digest)``, which buys two
things: the lookup is an indexed point query rather than a scan, and creation is
idempotent — proposing the same program twice in one run reuses the record
instead of opening a second pending approval and burning a round.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Deliberately not "tool.execute": those are the records graph_resume_target
# refuses to resume, and keeping the populations separate keeps the audit
# readable.
CODE_APPROVAL_ACTION_TYPE = "code.execute"
MAX_CODE_APPROVAL_ROUNDS = 3


def code_digest(code: str) -> str:
    """sha256 of the exact bytes that would run. No normalization."""
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


def code_approval_request_id(run_request_id: str, digest: str) -> str:
    """Stable id for one program in one run.

    ``approval_requests.request_id`` is ``String(36)``, so this cannot be a
    concatenation — a uuid5 keeps the width and stays deterministic, the same
    trick ``master.approval_request_id`` uses for per-round ids.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"cyberguard/code-approval/{run_request_id}/{digest}"))


async def find_approved(db: AsyncSession, request_id: str, digest: str):
    """An approved record authorizing exactly this code in exactly this run."""
    from app.models.approval import ApprovalRequest

    return (
        await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.request_id == code_approval_request_id(request_id, digest),
                ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE,
                ApprovalRequest.status == "approved",
            )
        )
    ).scalar_one_or_none()


async def count_rounds(db: AsyncSession, request_id: str) -> int:
    """How many distinct programs this run has already put up for approval."""
    from app.models.approval import ApprovalRequest

    return int(
        (
            await db.execute(
                select(func.count(ApprovalRequest.id)).where(
                    ApprovalRequest.action_type == CODE_APPROVAL_ACTION_TYPE,
                    ApprovalRequest.payload["run_request_id"].as_string() == request_id,
                )
            )
        ).scalar()
        or 0
    )


async def create_pending(
    db: AsyncSession, *, request_id: str, digest: str, code: str,
    user_id: int, agent_id: Optional[int], agent_name: Optional[str],
):
    """Open an approval carrying the full code, so a human reviews what runs.

    Idempotent per ``(run, digest)``: re-proposing the same program returns the
    existing record.
    """
    from app.models.approval import ApprovalRequest
    from app.services.approval_service import ApprovalService

    record_id = code_approval_request_id(request_id, digest)
    existing = (
        await db.execute(
            select(ApprovalRequest).where(ApprovalRequest.request_id == record_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return await ApprovalService.create_request(
        request_id=record_id,
        user_id=user_id,
        action_type=CODE_APPROVAL_ACTION_TYPE,
        action_description=(
            f"Agent {agent_name!r} proposes running {len(code)} characters of Python"
        ),
        agent_id=agent_id,
        agent_name=agent_name,
        payload={
            "run_request_id": request_id,
            "code_digest": digest,
            "code": code,
            "approval_type": "separation_of_duties",
        },
        risk_level="high",
        urgency="urgent",
    )
