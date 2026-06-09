"""Governance rollback API router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.models.rollback import RollbackRegistration
from app.services.safety_envelope import execute_rollback

router = APIRouter()


@router.get("/governance/rollback")
async def list_rollbacks(db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.SETTINGS_READ))):
    rows = (await db.execute(select(RollbackRegistration).where(
        RollbackRegistration.status == "registered"))).scalars().all()
    return [{"action_id": r.action_id, "tool": r.tool_name, "expires_at": r.expires_at} for r in rows]


@router.post("/governance/rollback/{action_id}")
async def trigger_rollback(action_id: str,
                           _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    ok = await execute_rollback(action_id)
    if not ok:
        raise HTTPException(409, "rollback failed or not available (see audit/paging)")
    return {"action_id": action_id, "status": "reverted"}
