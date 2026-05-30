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

    from datetime import datetime, timezone
    config = {
        "version": "1.0.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
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
    Performs conflict resolution: skips items that already exist (by name/id).
    """
    required_keys = ["version", "agents", "skills", "tools", "knowledge_bases"]
    for key in required_keys:
        if key not in config:
            return {"status": "error", "detail": f"Missing required key: {key}"}

    imported = {"agents": 0, "skills": 0, "tools": 0, "knowledge_bases": 0}
    errors = []

    # Import agents
    from sqlalchemy import select
    from app.models import AgentConfig
    for agent_data in config.get("agents", []):
        try:
            existing = await db.execute(
                select(AgentConfig).where(AgentConfig.agent_name == agent_data.get("agent_name"))
            )
            if existing.scalar_one_or_none():
                continue  # skip existing
            agent = AgentConfig(
                agent_name=agent_data.get("agent_name"),
                backend_type=agent_data.get("backend_type", "custom"),
                endpoint_url=agent_data.get("endpoint_url"),
                description=agent_data.get("description"),
                permission_level=agent_data.get("permission_level", "medium"),
                is_active=True,
            )
            db.add(agent)
            imported["agents"] += 1
        except Exception as e:
            errors.append(f"agent {agent_data.get('agent_name')}: {e}")

    # Import skills
    from app.models import Skill
    for skill_data in config.get("skills", []):
        try:
            existing = await db.execute(
                select(Skill).where(Skill.name == skill_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            skill = Skill(
                name=skill_data.get("name"),
                description=skill_data.get("description"),
                md_content=skill_data.get("md_content", ""),
                version=skill_data.get("version", "1.0.0"),
                is_active=True,
            )
            db.add(skill)
            imported["skills"] += 1
        except Exception as e:
            errors.append(f"skill {skill_data.get('name')}: {e}")

    # Import tools
    from app.models import Tool
    for tool_data in config.get("tools", []):
        try:
            existing = await db.execute(
                select(Tool).where(Tool.name == tool_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            tool = Tool(
                name=tool_data.get("name"),
                description=tool_data.get("description"),
                md_content=tool_data.get("md_content", ""),
                permission_level=tool_data.get("permission_level", "medium"),
                requires_approval=tool_data.get("requires_approval", False),
                is_active=True,
            )
            db.add(tool)
            imported["tools"] += 1
        except Exception as e:
            errors.append(f"tool {tool_data.get('name')}: {e}")

    # Import knowledge bases
    from app.models import KnowledgeBase
    for kb_data in config.get("knowledge_bases", []):
        try:
            existing = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.name == kb_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            kb = KnowledgeBase(
                name=kb_data.get("name"),
                description=kb_data.get("description"),
                embedding_model=kb_data.get("embedding_model", ""),
                rerank_model=kb_data.get("rerank_model", ""),
                is_active=True,
            )
            db.add(kb)
            imported["knowledge_bases"] += 1
        except Exception as e:
            errors.append(f"knowledge_base {kb_data.get('name')}: {e}")

    await db.commit()

    return {
        "status": "ok",
        "detail": "Import completed",
        "imported": imported,
        "errors": errors if errors else None,
    }
