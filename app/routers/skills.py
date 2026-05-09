"""Skill and Tool pool management router."""
import tempfile
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.skill import (
    SkillCreate, SkillRead, SkillUpdate, SkillListResponse,
    ToolCreate, ToolRead, ToolUpdate, ToolListResponse,
    SkillInstallUrlRequest, SkillInstallResponse,
)
from app.models.skill import Skill, Tool
from sqlalchemy import select, func

router = APIRouter()


# --- Skills ---
@router.get("/skills", response_model=SkillListResponse)
async def list_skills(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_READ))):
    total_result = await db.execute(select(func.count(Skill.id)))
    total = total_result.scalar()
    result = await db.execute(select(Skill).offset(skip).limit(limit))
    skills = result.scalars().all()
    return SkillListResponse(total=total, skills=[SkillRead.model_validate(s) for s in skills])


@router.post("/skills", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
async def create_skill(body: SkillCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_WRITE))):
    existing = await db.execute(select(Skill).where(Skill.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Skill name already exists")
    skill = Skill(**body.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return SkillRead.model_validate(skill)


@router.get("/skills/{skill_id}", response_model=SkillRead)
async def get_skill(skill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_READ))):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillRead.model_validate(skill)


@router.put("/skills/{skill_id}", response_model=SkillRead)
async def update_skill(skill_id: int, body: SkillUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_WRITE))):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(skill, key, value)
    await db.commit()
    await db.refresh(skill)
    return SkillRead.model_validate(skill)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_WRITE))):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()


@router.post("/skills/install/url", response_model=SkillInstallResponse)
async def install_skill_from_url(
    body: SkillInstallUrlRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SKILL_WRITE)),
):
    """Install a skill by fetching its markdown from a URL."""
    from app.services.skill_installer import install_skill_from_url as fetch_and_parse

    result = await fetch_and_parse(body.url, body.headers)
    if not result["success"]:
        return SkillInstallResponse(success=False, error=result["error"])

    skill_data = result["skill_data"]

    # Upsert: update existing skill with same name, or create new
    existing = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
    existing_skill = existing.scalar_one_or_none()

    if existing_skill:
        for key, value in skill_data.items():
            setattr(existing_skill, key, value)
        skill = existing_skill
    else:
        skill = Skill(**skill_data)
        db.add(skill)

    await db.commit()
    await db.refresh(skill)
    return SkillInstallResponse(success=True, skill=SkillRead.model_validate(skill))


@router.post("/skills/import", response_model=SkillInstallResponse)
async def import_skill_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SKILL_WRITE)),
):
    """Import a skill from an uploaded .md or .json file."""
    from app.services.skill_installer import install_skill_from_content

    if not file.filename:
        return SkillInstallResponse(success=False, error="No filename provided")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return SkillInstallResponse(success=False, error="File must be UTF-8 encoded")

    result = install_skill_from_content(file.filename, text)
    if not result["success"]:
        return SkillInstallResponse(success=False, error=result["error"])

    skill_data = result["skill_data"]

    # Upsert
    existing = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
    existing_skill = existing.scalar_one_or_none()

    if existing_skill:
        for key, value in skill_data.items():
            setattr(existing_skill, key, value)
        skill = existing_skill
    else:
        skill = Skill(**skill_data)
        db.add(skill)

    await db.commit()
    await db.refresh(skill)
    return SkillInstallResponse(success=True, skill=SkillRead.model_validate(skill))


# --- Tools ---
@router.get("/tools", response_model=ToolListResponse)
async def list_tools(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_READ))):
    total_result = await db.execute(select(func.count(Tool.id)))
    total = total_result.scalar()
    result = await db.execute(select(Tool).offset(skip).limit(limit))
    tools = result.scalars().all()
    return ToolListResponse(total=total, tools=[ToolRead.model_validate(t) for t in tools])


@router.post("/tools", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(body: ToolCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_WRITE))):
    existing = await db.execute(select(Tool).where(Tool.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tool name already exists")
    tool = Tool(**body.model_dump())
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return ToolRead.model_validate(tool)


@router.get("/tools/{tool_id}", response_model=ToolRead)
async def get_tool(tool_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_READ))):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolRead.model_validate(tool)


@router.put("/tools/{tool_id}", response_model=ToolRead)
async def update_tool(tool_id: int, body: ToolUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_WRITE))):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(tool, key, value)
    await db.commit()
    await db.refresh(tool)
    return ToolRead.model_validate(tool)


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(tool_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_WRITE))):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    await db.delete(tool)
    await db.commit()
