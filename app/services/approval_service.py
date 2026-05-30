"""Approval service — shared between LangGraph nodes and the REST API.

Cross-process signalling uses Redis pub/sub on channel `approval:{request_id}`.
This works correctly when the Master Agent runs in a Celery worker process and
the admin calls POST /approvals/{id}/decide in the FastAPI process.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.approval import ApprovalRequest

logger = logging.getLogger(__name__)

_APPROVAL_CHANNEL_PREFIX = "approval:"
_POLL_INTERVAL = 2.0  # seconds between DB poll fallback


class ApprovalService:
    """Service for managing human-in-the-loop approval requests."""

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
        """Write a pending approval request to DB and publish to Redis channel."""
        expires_at = None
        if expires_in_minutes:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)

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

        # Notify waiting workers via approval-specific Redis channel
        await ApprovalService._publish(request_id, "created")

        # Publish to admin events channel so SSE listeners see the new request
        await ApprovalService._publish_admin_event({
            "event": "new_request",
            "request_id": request_id,
            "action_type": action_type,
            "risk_level": risk_level,
        })

        # Email admin (best-effort, fire-and-forget)
        asyncio.create_task(ApprovalService._email_admin_created(
            request_id=request_id,
            action_description=action_description,
            risk_level=risk_level,
            user_id=user_id,
        ))

        # Fan out to outgoing webhooks subscribed to approval.required (non-blocking)
        try:
            from app.services.webhook_service import emit
            asyncio.create_task(emit("approval.required", {
                "request_id": request_id,
                "user_id": user_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "action_type": action_type,
                "action_description": action_description,
                "risk_level": risk_level,
                "urgency": urgency,
                "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
            }))
        except Exception as e:
            logger.warning(f"[approval] webhook emit failed: {e}")

        logger.info(
            f"[approval] Created request {record.id} for request_id={request_id} "
            f"action={action_type} risk={risk_level}"
        )
        return record

    @staticmethod
    async def _publish(request_id: str, event: str) -> None:
        """Publish an event to the per-request Redis channel (best-effort)."""
        try:
            from app.core.redis_client import get_redis
            r = await get_redis()
            channel = f"{_APPROVAL_CHANNEL_PREFIX}{request_id}"
            await r.publish(channel, json.dumps({"event": event, "request_id": request_id}))
        except Exception as e:
            logger.warning(f"[approval] Redis publish failed for {request_id}: {e}")

    @staticmethod
    async def _publish_admin_event(payload: dict) -> None:
        """Publish to the shared admin SSE channel (best-effort)."""
        try:
            from app.core.redis_client import get_redis
            r = await get_redis()
            await r.publish("approval:admin:events", json.dumps(payload))
        except Exception as e:
            logger.warning(f"[approval] Admin event publish failed: {e}")

    @staticmethod
    async def _email_admin_created(
        request_id: str,
        action_description: str,
        risk_level: str,
        user_id: int,
    ) -> None:
        try:
            from app.services.email_service import notify_approval_created
            await notify_approval_created(
                request_id=request_id,
                action_description=action_description,
                risk_level=risk_level,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"[approval] Email notify failed: {e}")

    @staticmethod
    async def wait_for_decision(
        request_id: str,
        timeout_seconds: int = 3600,
    ) -> tuple[str, Optional[str]]:
        """Wait for a human to approve or reject a request.

        Uses Redis pub/sub for cross-process notification, with a DB-poll
        fallback every _POLL_INTERVAL seconds in case the pub/sub message
        is missed (e.g. network blip or Redis restart).

        Returns (status, approver_comment).
        Raises asyncio.TimeoutError if timeout reached.
        """
        from app.config import settings

        if settings.AUTO_APPROVE:
            logger.info(f"[approval] AUTO_APPROVE — auto-approving request_id={request_id}")
            await ApprovalService.decide(request_id, "approved", approver_id=0, comment="Auto-approved by system")
            return "approved", "Auto-approved by system"

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        channel = f"{_APPROVAL_CHANNEL_PREFIX}{request_id}"

        try:
            from app.core.redis_client import get_redis
            r = await get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(channel)
        except Exception as e:
            logger.warning(f"[approval] Redis subscribe failed, falling back to DB-poll only: {e}")
            pubsub = None

        try:
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return "expired", None

                # DB poll — authoritative source of truth
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(ApprovalRequest).where(
                            ApprovalRequest.request_id == request_id
                        )
                    )
                    record = result.scalar_one_or_none()

                if record and record.status in ("approved", "rejected"):
                    return record.status, record.approver_comment

                # Wait for pub/sub message or poll interval (whichever comes first)
                wait_secs = min(_POLL_INTERVAL, remaining)
                if pubsub:
                    try:
                        msg = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True, timeout=wait_secs),
                            timeout=wait_secs + 0.5,
                        )
                        # Any message means the decision is ready — loop back to DB poll
                    except (asyncio.TimeoutError, Exception):
                        pass
                else:
                    await asyncio.sleep(wait_secs)

        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:
                    pass

    @staticmethod
    async def decide(
        request_id: str,
        decision: str,
        approver_id: int,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """Record an approval/rejection decision and notify waiting workers via Redis."""
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
            record.decided_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(record)

        # Publish decision to Redis so all waiting workers wake up immediately
        await ApprovalService._publish(request_id, decision)

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
