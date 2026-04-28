"""Audit log router."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.audit import AuditLogRead, AuditLogListResponse
from app.models.audit import AuditLog
from sqlalchemy import select, func, desc

router = APIRouter()


@router.get("/audit/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = 0,
    limit: int = 100,
    user_id: int | None = Query(None),
    agent_id: int | None = Query(None),
    action: str | None = Query(None),
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

    total_result = await db.execute(select(func.count(AuditLog.id)))
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
        writer = csv.DictWriter(output, fieldnames=["id", "user_id", "agent_id", "action", "input_hash", "output_hash", "timestamp"])
        writer.writeheader()
        for log in logs:
            writer.writerow({
                "id": log.id,
                "user_id": log.user_id,
                "agent_id": log.agent_id,
                "action": log.action,
                "input_hash": log.input_hash,
                "output_hash": log.output_hash,
                "timestamp": log.timestamp.isoformat() if log.timestamp else "",
            })
        return {
            "format": "csv",
            "content": output.getvalue(),
            "filename": f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        }

    return {
        "format": "json",
        "logs": [AuditLogRead.model_validate(l).model_dump() for l in logs],
        "filename": f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
    }
