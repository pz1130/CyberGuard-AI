"""Governance metrics API router."""
from fastapi import APIRouter, Depends
from app.core.dependencies import require_permission
from app.core.rbac import Permission
from app.services.governance_metrics import collect

router = APIRouter()


@router.get("/governance/metrics")
async def governance_metrics(window_days: int = 30,
                             _=Depends(require_permission(Permission.SETTINGS_READ))):
    return await collect(window_days=window_days)
