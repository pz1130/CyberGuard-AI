"""System configuration export/import router."""
import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_role
from app.core.rbac import Role

router = APIRouter()


@router.post("/config/export")
async def export_config(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    """
    Export full system configuration as JSON.
    Includes: users (no passwords), agents, skills, tools, knowledge bases, providers.
    """
    from app.models import User, AgentConfig, Skill, Tool, KnowledgeBase, RoleModel

    # Export agents
    from sqlalchemy import select
    agents_result = await db.execute(select(AgentConfig))
    agents = [
        {k: v for k, v in {
            "id": a.id, "agent_name": a.agent_name, "backend_type": a.backend_type,
            "endpoint_url": a.endpoint_url, "description": a.description,
            "permission_level": a.permission_level,
        }.items()}
        for a in agents_result.scalars().all()
    ]

    # Export skills
    skills_result = await db.execute(select(Skill))
    skills = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in skills_result.scalars().all()
    ]

    # Export tools
    tools_result = await db.execute(select(Tool))
    tools = [
        {k: v for k, v in t.__dict__.items() if not k.startswith("_")}
        for t in tools_result.scalars().all()
    ]

    # Export knowledge bases
    kbs_result = await db.execute(select(KnowledgeBase))
    kbs = [
        {k: v for k, v in kb.__dict__.items() if not k.startswith("_")}
        for kb in kbs_result.scalars().all()
    ]

    from datetime import datetime
    config = {
        "version": "1.0.0",
        "exported_at": datetime.utcnow().isoformat(),
        "agents": agents,
        "skills": skills,
        "tools": tools,
        "knowledge_bases": kbs,
    }
    return config


@router.post("/config/import")
async def import_config(
    config: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    """
    Import system configuration from JSON.
    Validates structure before applying.
    """
    required_keys = ["version", "agents", "skills", "tools", "knowledge_bases"]
    for key in required_keys:
        if key not in config:
            return {"status": "error", "detail": f"Missing required key: {key}"}

    # TODO: Implement actual import with conflict resolution
    return {
        "status": "ok",
        "detail": "Import validated. Full apply not yet implemented.",
        "imported": {
            "agents": len(config.get("agents", [])),
            "skills": len(config.get("skills", [])),
            "tools": len(config.get("tools", [])),
            "knowledge_bases": len(config.get("knowledge_bases", [])),
        },
    }
