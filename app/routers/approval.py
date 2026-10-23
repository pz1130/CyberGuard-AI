"""Approval requests REST API + SSE push."""
from typing import Optional
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.models.approval import ApprovalRequest
from app.schemas.approval import (
    ApprovalRequestResponse,
    ApprovalDecision,
    ApprovalListResponse,
)
from app.services.approval_service import (
    ApprovalService,
    ApprovalExpiredError,
    SelfApprovalError,
)

router = APIRouter()

# Approvals raised by the master graph's approval node. Everything else — most
# notably the internal agent's per-tool approvals — has no checkpointed graph
# behind it, and asking to resume one only produces a failing Celery task.
_GRAPH_APPROVAL_ACTION_TYPES = {"agent_execution"}


def graph_resume_target(record) -> Optional[dict]:
    """Resume arguments for *record*, or None if it is not a graph approval.

    The thread_id must come from the payload: falling back to ``request_id``
    invents a thread that was never suspended.
    """
    if getattr(record, "action_type", None) not in _GRAPH_APPROVAL_ACTION_TYPES:
        return None
    payload = getattr(record, "payload", None) or {}
    thread_id = payload.get("thread_id")
    if not thread_id:
        return None
    return {
        "thread_id": thread_id,
        "execution_id": payload.get("execution_id"),
        "conversation_id": payload.get("conversation_id"),
        "user_input": payload.get("user_input"),
    }


logger = logging.getLogger(__name__)


@router.get("/approvals/notify-status")
async def approval_notify_status(
    _=Depends(require_permission(Permission.APPROVAL_READ)),
):
    """Whether approval emails will actually send."""
    from app.services.email_config import load_email_config, config_status
    return config_status(await load_email_config())


@router.get("/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    status_filter: str = "pending",
    _=Depends(require_permission(Permission.APPROVAL_READ)),
    session: AsyncSession = Depends(get_db_session),
):
    """List approval requests (approval permission required). ?status_filter=pending|approved|rejected|all"""
    await ApprovalService.expire_pending()
    query = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status_filter != "all":
        query = query.where(ApprovalRequest.status == status_filter)
    result = await session.execute(query)
    records = list(result.scalars().all())
    return ApprovalListResponse(
        requests=[ApprovalRequestResponse.model_validate(r) for r in records],
        total=len(records),
    )


@router.get("/approvals/events")
async def approval_sse_events(
    current_user: AuthenticatedUser = Depends(require_permission(Permission.APPROVAL_READ)),
):
    """SSE stream for real-time approval notifications (approval permission required).

    Connect at GET /api/v1/approvals/events.
    Each event: ``data: {JSON}\\n\\n``

    Uses Redis pub/sub on channel ``approval:admin:events`` for low-latency
    push, with a 2-second DB-poll heartbeat as fallback.
    """
    admin_channel = "approval:admin:events"

    async def event_stream():
        seen_ids: set[int] = set()
        pubsub = None

        # Seed already-pending IDs so we don't replay old events on connect
        try:
            existing = await ApprovalService.list_pending()
            seen_ids = {r.id for r in existing}
            # Send current pending count as initial event
            yield (
                f"data: {json.dumps({'type': 'connected', 'pending': len(seen_ids)})}\n\n"
            )
        except Exception:
            pass

        # Subscribe to Redis admin channel
        try:
            from app.core.redis_client import get_redis
            r = await get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(admin_channel)
        except Exception as e:
            logger.warning(f"[approval SSE] Redis subscribe failed: {e}")

        try:
            while True:
                # Wait for Redis notification or 10-second heartbeat
                got_msg = False
                if pubsub:
                    try:
                        msg = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True, timeout=10),
                            timeout=10.5,
                        )
                        if msg:
                            got_msg = True
                    except (asyncio.TimeoutError, Exception):
                        pass

                if not got_msg:
                    # Heartbeat so the client knows the connection is alive
                    yield ": heartbeat\n\n"

                # Always re-check DB for new pending requests
                try:
                    pending = await ApprovalService.list_pending()
                    new_ids = {r.id for r in pending} - seen_ids
                    for rid in sorted(new_ids):
                        record = next(r for r in pending if r.id == rid)
                        payload = ApprovalRequestResponse.model_validate(record).model_dump(mode="json")
                        payload["type"] = "new_request"
                        yield f"data: {json.dumps(payload)}\n\n"
                        seen_ids.add(rid)
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe(admin_channel)
                    await pubsub.close()
                except Exception:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    approval_id: int,
    _=Depends(require_permission(Permission.APPROVAL_READ)),
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
    current_user: AuthenticatedUser = Depends(require_permission(Permission.APPROVAL_DECIDE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve or reject a pending request (approval permission required)."""
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
            approver_id=current_user.user_id,
            comment=body.comment,
        )
    except SelfApprovalError as e:
        from app.core.audit import record_action
        await record_action(
            user_id=current_user.user_id,
            action="approval.decide.denied",
            human_reviewer=str(current_user.user_id),
            risk_tier=record.risk_level,
            input_data={
                "request_id": record.request_id,
                "decision": body.decision,
            },
            output_data={"status": "denied", "reason": "self_approval"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ApprovalExpiredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    from app.core.audit import record_action
    await record_action(user_id=current_user.user_id, action="approval.decide",
                        human_reviewer=str(current_user.user_id), risk_tier=record.risk_level,
                        input_data={"request_id": record.request_id, "decision": body.decision},
                        output_data={"status": updated.status})

    # Resume a master graph suspended via interrupt(). Only approvals raised by
    # the graph's approval node have a checkpointed thread to resume.
    target = graph_resume_target(record)
    if target is not None:
        try:
            from app.workers.tasks import resume_master_agent_task
            resume_master_agent_task.delay(
                decision=body.decision,
                comment=body.comment,
                user_id=record.user_id,
                **target,
            )
        except Exception as e:  # noqa: BLE001 - dispatch failure must not 500 the decision
            logger.warning("[approval] resume dispatch failed: %s", e)

    # Send email notification to requester (best-effort, non-blocking)
    asyncio.create_task(_notify_decision(record, body.decision, body.comment))

    return ApprovalRequestResponse.model_validate(updated)


async def _notify_decision(record: ApprovalRequest, decision: str, comment: Optional[str]):
    """Fire-and-forget email when an approval decision is made."""
    try:
        from app.services.email_service import notify_approval_decided
        from app.core.database import AsyncSessionLocal
        from app.models.user import User
        # Fetch requester email
        async with AsyncSessionLocal() as session:
            user_result = await session.execute(
                select(User).where(User.id == record.user_id)
            )
            user = user_result.scalar_one_or_none()
        if user and user.email:
            await notify_approval_decided(
                to_email=user.email,
                request_id=record.request_id,
                decision=decision,
                comment=comment,
            )
    except Exception as e:
        logger.warning(f"[approval] notify_decision failed: {e}")
