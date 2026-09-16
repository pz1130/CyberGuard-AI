"""Audit log router."""
from typing import Optional
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import AuthenticatedUser
from app.core.dependencies import get_current_user, get_db, require_permission
from app.core.rbac import Permission
from app.schemas.audit import AuditLogRead, AuditLogListResponse
from app.models.audit import AuditLog
from sqlalchemy import select, func, desc

router = APIRouter()


@router.get("/audit/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = Query(None),
    agent_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """List audit logs with optional filters."""
    query = select(AuditLog)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if agent_id:
        query = query.where(AuditLog.agent_id == agent_id)
    if action:
        query = query.where(AuditLog.action == action)

    total_result = await db.execute(select(func.count(AuditLog.id)).where(
        (AuditLog.user_id == user_id if user_id else True) &
        (AuditLog.agent_id == agent_id if agent_id else True) &
        (AuditLog.action == action if action else True)
    ))
    total = total_result.scalar()

    query = query.order_by(desc(AuditLog.timestamp)).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogListResponse(total=total, logs=[AuditLogRead.model_validate(l) for l in logs])


@router.get("/audit/export")
async def export_audit_logs(
    format: str = "json",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """Export audit logs in SIEM-compatible format (JSON or CSV)."""
    result = await db.execute(select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(10000))
    logs = result.scalars().all()

    if format == "csv":
        import csv, io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "user_id", "agent_id", "action", "input_hash", "output_hash",
            "prev_hash", "entry_hash", "timestamp",
        ])
        writer.writeheader()
        for log in logs:
            writer.writerow({
                "id": log.id,
                "user_id": log.user_id,
                "agent_id": log.agent_id,
                "action": log.action,
                "input_hash": log.input_hash,
                "output_hash": log.output_hash,
                "prev_hash": log.prev_hash,
                "entry_hash": log.entry_hash,
                "timestamp": log.timestamp.isoformat() if log.timestamp else "",
            })
        return {
            "format": "csv",
            "content": output.getvalue(),
            "filename": f"audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
        }

    return {
        "format": "json",
        "logs": [AuditLogRead.model_validate(l).model_dump() for l in logs],
        "filename": f"audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
    }


from app.core.audit import verify_chain


@router.get("/audit/verify")
async def audit_verify(
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    ok, broken_at = await verify_chain()
    return {"intact": ok, "first_broken_row_id": broken_at}


from app.services.audit_worm import export_new


@router.post("/audit/worm-export")
async def audit_worm_export(
    retain_days: int = 365,
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    return await export_new(retain_days=retain_days)


@router.get("/audit/conversation-search")
async def auditor_conversation_search(
    q: str = "",
    user_id: Optional[int] = None,
    limit: int = 20,
    cursor: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """Search chat messages across users, for an investigation.

    Separate from the self-service search on purpose: that endpoint takes the
    owner from the token and accepts no user_id, so it cannot be turned into
    this by passing a parameter. Omitting `user_id` searches everyone.

    Sees what ordinary search hides — conversations a person deleted, and
    internal agents' memory slices. A tombstone is the whole reason delete does
    not delete, and a slice is where an agent's own reasoning lives.
    """
    from fastapi import HTTPException

    from app.core.audit import record_action
    from app.services.message_search import search_messages
    from app.services.message_snippet import snippet

    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="q is required")

    hits = await search_messages(
        db, user_id=user_id, term=term, limit=limit, cursor=cursor,
        include_hidden=True)

    # Reading someone's private conversations is the act that needs a trace,
    # or "who watches the watchers" has no answer here.
    await record_action(
        user_id=current_user.user_id,
        action="audit.conversation_search",
        action_category="observe",
        risk_tier="medium",
        rollback_possible=True,
        input_data={"query": term, "scope_user_id": user_id},
        output_data={"results": len(hits)},
    )

    return {
        "results": [
            {
                "conversation_id": hit.conversation_id,
                "conversation_title": hit.conversation_title,
                "user_id": hit.user_id,
                "username": hit.username,
                "hits": hit.hits,
                "matches": [
                    {
                        "message_id": m.message_id,
                        "seq": m.seq,
                        "role": m.role,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                        "snippet": snippet(m.content, term),
                    }
                    for m in hit.matches
                ],
            }
            for hit in hits
        ],
        # The newest match of the last conversation on this page.
        "next_cursor": (hits[-1].matches[0].message_id
                        if hits and hits[-1].matches else None),
    }
