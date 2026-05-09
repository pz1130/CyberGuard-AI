"""Approval requests REST API."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_role
from app.core.rbac import Role, Permission
from app.core.auth import AuthenticatedUser
from app.schemas.approval import (
    ApprovalRequestCreate,
    ApprovalRequestResponse,
    ApprovalDecision,
    ApprovalListResponse,
)
from app.services.approval_service import ApprovalService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    status_filter: str = "pending",  # pending / approved / rejected / all
    _=Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """List approval requests. ADMIN only."""
    from sqlalchemy import select
    from app.models.approval import ApprovalRequest

    query = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())

    if status_filter != "all":
        query = query.where(ApprovalRequest.status == status_filter)

    result = await session.execute(query)
    records = list(result.scalars().all())

    return ApprovalListResponse(
        requests=[ApprovalRequestResponse.model_validate(r) for r in records],
        total=len(records),
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    approval_id: int,
    _=Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a specific approval request by ID."""
    record = await ApprovalService.get_by_id(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalRequestResponse.model_validate(record)


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalRequestResponse)
async def decide_approval(
    approval_id: int,
    body: ApprovalDecision,
    current_user: AuthenticatedUser = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve or reject a pending request. ADMIN only."""
    from sqlalchemy import select
    from app.models.approval import ApprovalRequest

    # Fetch request_id from DB
    result = await session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if record.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already {record.status}, cannot decide again",
        )

    try:
        updated = await ApprovalService.decide(
            request_id=record.request_id,
            decision=body.decision,
            approver_id=approver.id,
            comment=body.comment,
        )
        return ApprovalRequestResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/approvals/sse")
async def approval_sse(
    _=Depends(require_role(Role.ADMIN)),
):
    """SSE stream of new pending approval requests.

    Admin dashboard can listen at GET /api/v1/approvals/sse
    to receive real-time notifications when new approval requests arrive.

    Each event: "data: {json payload}\\n\\n"
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    async def event_generator():
        # Poll DB every 2 seconds and yield when new pending requests appear
        seen_ids: set[int] = set()
        while True:
            try:
                pending = await ApprovalService.list_pending()
                new_ids = {r.id for r in pending} - seen_ids
                if new_ids:
                    for rid in sorted(new_ids):
                        record = next(r for r in pending if r.id == rid)
                        yield f"data: {json.dumps(ApprovalRequestResponse.model_validate(record).model_dump(mode='json'))}\n\n"
                        seen_ids.add(rid)
            except Exception as e:
                yield f"data: {{\"error\": \"{e}}}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


# Type hint for User model (used in decide endpoint)
from app.models.user import User
