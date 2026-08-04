"""Kill switch API router."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services import kill_switch as ks
from app.core.dependencies import require_permission
from app.core.rbac import Permission

router = APIRouter()


class HaltBody(BaseModel):
    reason: str | None = None


@router.post("/agents/halt", tags=["Kill Switch"])
async def halt_all(body: HaltBody, _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    await ks.engage("global", by="api", reason=body.reason)
    return {"halted": True, "scope": "global"}


@router.delete("/agents/halt", tags=["Kill Switch"])
async def resume_all(_=Depends(require_permission(Permission.SETTINGS_WRITE))):
    await ks.clear("global")
    return {"halted": False, "scope": "global"}


@router.post("/agents/{agent_id}/halt", tags=["Kill Switch"])
async def halt_agent(agent_id: int, body: HaltBody, _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    await ks.engage(f"agent:{agent_id}", by="api", reason=body.reason)
    return {"halted": True, "scope": f"agent:{agent_id}"}


@router.get("/agents/halt/status", tags=["Kill Switch"])
async def halt_status(_=Depends(require_permission(Permission.SETTINGS_READ))):
    return {"global": await ks.is_halted()}
