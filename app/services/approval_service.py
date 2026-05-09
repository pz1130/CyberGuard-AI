"""Approval service — shared between LangGraph nodes and the REST API."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.approval import ApprovalRequest
from app.schemas.approval import ApprovalRequestCreate

logger = logging.getLogger(__name__)

# In-memory set of pending request_ids waiting for WebSocket push
# Key = request_id, Value = asyncio.Event for cancellation
_pending_events: dict[str, asyncio.Event] = {}


class ApprovalService:
    """Service for managing human-in-the-loop approval requests.

    Used by:
    1. MasterAgent._approval_node  — to create a request and WAIT
    2. approval router             — to list/decide requests
    3. WebSocket SSE               — to push notifications to admin dashboard
    """

    @staticmethod
    async def create_request(
        *,
        request_id: str,
        user_id: int,
        action_type: str,
        action_description: str,
        agent_id: Optional[int] = None,
        agent_name: Optional[str] = None,
        payload: Optional[dict] = None,
        risk_level: str = "medium",
        urgency: str = "normal",
        expires_in_minutes: Optional[int] = 60,
    ) -> ApprovalRequest:
        """Write a pending approval request to DB and signal WebSocket listeners."""
        expires_at = None
        if expires_in_minutes:
            expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

        async with AsyncSessionLocal() as session:
            record = ApprovalRequest(
                request_id=request_id,
                user_id=user_id,
                agent_id=agent_id,
                agent_name=agent_name,
                action_type=action_type,
                action_description=action_description,
                payload=payload or {},
                risk_level=risk_level,
                urgency=urgency,
                status="pending",
                expires_at=expires_at,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

        # Signal any waiting SSE/WebSocket listeners
        if request_id in _pending_events:
            _pending_events[request_id].set()

        logger.info(
            f"[approval] Created request {record.id} for request_id={request_id} "
            f"action={action_type} risk={risk_level}"
        )
        return record

    @staticmethod
    async def wait_for_decision(
        request_id: str,
        timeout_seconds: int = 3600,
    ) -> tuple[str, Optional[str]]:
        """Wait for a human to approve or reject a request.

        Called by MasterAgent._approval_node to suspend graph execution
        until a decision arrives.

        Returns (status, approver_comment) where status is "approved" or "rejected".
        Raises asyncio.TimeoutError if timeout reached.

        If settings.AUTO_APPROVE is True, auto-approves immediately.
        """
        from app.config import settings

        # Auto-approve mode — skip human-in-the-loop
        if settings.AUTO_APPROVE:
            logger.info(f"[approval] AUTO_APPROVE enabled — auto-approving request_id={request_id}")
            await ApprovalService.decide(request_id, "approved", approver_id=0, comment="Auto-approved by system")
            return "approved", "Auto-approved by system"

        event = asyncio.Event()
        _pending_events[request_id] = event

        try:
            try:
                await asyncio.wait_for(
                    event.wait(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                return "expired", None

            # Re-fetch the record to get the decision
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.request_id == request_id
                    )
                )
                record = result.scalar_one_or_none()

            if record:
                return record.status, record.approver_comment
            return "expired", None

        finally:
            _pending_events.pop(request_id, None)

    @staticmethod
    async def decide(
        request_id: str,
        decision: str,  # "approved" or "rejected"
        approver_id: int,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """Record an approval/rejection decision and wake the waiting graph node."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.request_id == request_id,
                    ApprovalRequest.status == "pending",
                )
            )
            record = result.scalar_one_or_none()

            if not record:
                raise ValueError(f"No pending approval request found for {request_id}")

            if decision not in ("approved", "rejected"):
                raise ValueError(f"Invalid decision: {decision}. Must be 'approved' or 'rejected'.")

            record.status = decision
            record.approver_id = approver_id
            record.approver_comment = comment
            record.decided_at = datetime.utcnow()

            await session.commit()
            await session.refresh(record)

        # Wake the waiting graph node (if still waiting)
        if request_id in _pending_events:
            _pending_events[request_id].set()

        logger.info(f"[approval] Request {request_id} {decision} by approver_id={approver_id}")
        return record

    @staticmethod
    async def list_pending() -> list[ApprovalRequest]:
        """List all pending approval requests, newest first."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == "pending")
                .order_by(ApprovalRequest.created_at.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_by_id(approval_id: int) -> Optional[ApprovalRequest]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_request_id(request_id: str) -> Optional[ApprovalRequest]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.request_id == request_id)
            )
            return result.scalar_one_or_none()
