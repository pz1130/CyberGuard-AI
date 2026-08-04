"""Governance config API router."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.models.agent import AgentConfig
from app.services import governance_config as gc

router = APIRouter()


class GovernanceBody(BaseModel):
    autonomy_tier: str = "L2"
    l3_authorization_ref: str | None = None
    allowed_categories: list[str] | None = None
    auto_execute_min_confidence: float = 0.85
    escalate_to_human_below: float = 0.60
    pii_handling_policy: str = "redact"
    kill_switch_enabled: bool = True
    is_poc: bool = True
    requires_approval_rules: list[dict] | None = None


async def _get_agent(db: AsyncSession, agent_id: int) -> AgentConfig:
    agent = (await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))).scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, "agent not found")
    return agent


@router.get("/agents/{agent_id}/governance")
async def get_governance(agent_id: int, db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.SETTINGS_READ))):
    a = await _get_agent(db, agent_id)
    return {k: getattr(a, k) for k in GovernanceBody.model_fields}


@router.put("/agents/{agent_id}/governance")
async def put_governance(agent_id: int, body: GovernanceBody,
                         db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.SETTINGS_WRITE))):
    try:
        gc.validate_autonomy(body.autonomy_tier, body.l3_authorization_ref)
    except ValueError as e:
        raise HTTPException(400, str(e))
    a = await _get_agent(db, agent_id)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    await db.commit()
    return {"status": "updated", "agent_id": agent_id}


@router.get("/agents/{agent_id}/governance.yaml")
async def export_governance_yaml(agent_id: int, db: AsyncSession = Depends(get_db),
                                 _=Depends(require_permission(Permission.SETTINGS_READ))):
    a = await _get_agent(db, agent_id)
    return Response(content=gc.export_yaml(a), media_type="application/x-yaml")
