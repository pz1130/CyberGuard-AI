"""Skill and Tool pool management router."""
from typing import Any, Dict, List, Optional, Sequence
from fastapi import APIRouter, Depends, HTTPException, Response, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission, get_current_user
from app.core.rbac import Permission, Role, ROLE_PERMISSIONS
from app.services.tool_executor import execute_tool
from app.schemas.skill import (
    SkillCreate, SkillRead, SkillUpdate, SkillListResponse,
    ToolCreate, ToolRead, ToolUpdate, ToolListResponse,
    SkillInstallUrlRequest, SkillInstallResponse, SkillImportFailure,
    SkillFileRead, SkillFileListResponse, SkillScriptPromoteRequest,
)
from app.models.skill import Skill, SkillFile, Tool
from sqlalchemy import delete, select, func

router = APIRouter()

ALLOWED_SCRIPT_INTERPRETERS = ("python3", "sh")
EXECUTABLE_SCRIPT_SUFFIXES = (".py", ".sh")


async def validate_promotion(db: AsyncSession, skill_id: int, script_path: str, body):
    """Check a promotion request and return the Tool column dict.

    Every rule here is re-checked at execution; failing at review time means the
    approver sees the problem while they are looking at the script.
    """
    import json as _json
    import shlex

    from app.services.skill_bundle import bundle_digest, load_bundle
    from app.services.tool_executor import ToolArgError, build_argv

    if not script_path.lower().endswith(EXECUTABLE_SCRIPT_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"not an executable script: {script_path} "
                   f"(expected one of {', '.join(EXECUTABLE_SCRIPT_SUFFIXES)})",
        )
    if body.script_network != "none":
        raise HTTPException(
            status_code=400,
            detail=f"script_network={body.script_network!r} is not supported yet; "
                   "only 'none' is available in this phase",
        )

    files = await load_bundle(db, skill_id)
    if script_path not in {p for p, _ in files}:
        raise HTTPException(status_code=400, detail=f"{script_path} is not in the bundle")

    tokens = shlex.split(body.command_template)
    if not tokens or tokens[0] not in ALLOWED_SCRIPT_INTERPRETERS:
        raise HTTPException(
            status_code=400,
            detail=f"interpreter must be one of {', '.join(ALLOWED_SCRIPT_INTERPRETERS)}",
        )
    if len(tokens) < 2:
        raise HTTPException(status_code=400, detail="command_template must name the script")
    if tokens[1].startswith("-"):
        raise HTTPException(status_code=400, detail="interpreter flags are not permitted")
    if tokens[1] != script_path:
        raise HTTPException(
            status_code=400,
            detail=f"command_template must run {script_path}, not {tokens[1]}",
        )

    # Dry-run the real argv builder so placeholder mistakes surface at review.
    try:
        schema = _json.loads(body.input_schema_json) if body.input_schema_json else {}
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"input_schema_json is not JSON: {e}") from e
    probe = {k: "probe" for k in (schema.get("properties") or {})}
    try:
        build_argv(body.command_template, schema, probe)
    except ToolArgError as e:
        raise HTTPException(status_code=400, detail=f"command_template: {e}") from e

    return {
        "name": body.name,
        "description": body.description,
        "command_template": body.command_template,
        "input_schema_json": body.input_schema_json,
        "required_permission": body.required_permission,
        "action_category": body.action_category,
        "risk_tier": body.risk_tier,
        "permission_level": body.permission_level,
        "timeout_seconds": body.timeout_seconds,
        "is_active": True,
        "source_skill_id": skill_id,
        "source_script_path": script_path,
        "source_bundle_digest": bundle_digest(files),
        "script_network": body.script_network,
        "script_network_allowlist": None,
    }


async def _bundle_file_counts(db: AsyncSession, skill_ids: Sequence[int]) -> Dict[int, int]:
    """Bundled-file count per skill, in one grouped query."""
    if not skill_ids:
        return {}
    rows = await db.execute(
        select(SkillFile.skill_id, func.count(SkillFile.id))
        .where(SkillFile.skill_id.in_(list(skill_ids)))
        .group_by(SkillFile.skill_id)
    )
    return {skill_id: count for skill_id, count in rows.all()}


async def _to_read(db: AsyncSession, skills: Sequence[Skill]) -> List[SkillRead]:
    """Serialize skills with their bundled-file counts attached."""
    counts = await _bundle_file_counts(db, [s.id for s in skills])
    out = []
    for skill in skills:
        read = SkillRead.model_validate(skill)
        read.bundle_file_count = counts.get(skill.id, 0)
        out.append(read)
    return out


def _entry_bytes(entry: Dict[str, Any]) -> bytes:
    """Bytes of an importer file entry, whichever column it is destined for."""
    if entry.get("content_text") is not None:
        return entry["content_text"].encode("utf-8")
    return entry.get("content_blob") or b""


async def invalidate_stale_script_tools(db: AsyncSession, skill_id: int, digest: str):
    """Deactivate promoted tools whose approved bundle no longer matches.

    Approval binds to a specific bundle. When the bundle changes, the approval
    no longer covers the code that would run, so the tool goes dormant until an
    admin reviews it again. Failing here means failing visibly at import time
    rather than quietly at some later execution.

    Returns only the tools this call actually changed. ``is_active`` is filtered
    in Python as well as in the query so that contract does not depend on the
    query having been written a particular way.
    """
    rows = (
        await db.execute(
            select(Tool).where(Tool.source_skill_id == skill_id, Tool.is_active.is_(True))
        )
    ).scalars().all()
    stale = [t for t in rows if t.is_active and t.source_bundle_digest != digest]
    for tool in stale:
        tool.is_active = False
    return stale


async def _upsert_skill(
    db: AsyncSession,
    skill_data: Dict[str, Any],
    files: Optional[Sequence[Dict[str, Any]]] = None,
) -> Skill:
    """Create or update a skill by name and replace its bundled file set.

    The file set is replaced wholesale rather than merged so a re-import can
    never leave a path behind that the new bundle no longer ships.
    """
    existing = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
    skill = existing.scalar_one_or_none()

    if skill:
        for key, value in skill_data.items():
            setattr(skill, key, value)
    else:
        skill = Skill(**skill_data)
        db.add(skill)
    await db.flush()

    await db.execute(delete(SkillFile).where(SkillFile.skill_id == skill.id))
    for entry in files or []:
        db.add(SkillFile(skill_id=skill.id, **entry))

    # A changed bundle invalidates every approval granted against the old one.
    from app.core.audit import record_action
    from app.services.skill_bundle import bundle_digest

    digest = bundle_digest([(f["path"], _entry_bytes(f)) for f in (files or [])])
    for stale in await invalidate_stale_script_tools(db, skill.id, digest):
        await record_action(
            user_id=0, action="skill.script.invalidate",
            input_data={"skill_id": skill.id, "tool_id": stale.id,
                        "approved_digest": stale.source_bundle_digest,
                        "current_digest": digest},
            output_data={"deactivated": True},
        )
    return skill


# --- Skills ---
@router.get("/skills", response_model=SkillListResponse)
async def list_skills(skip: int = 0, limit: int = 50, tag: Optional[str] = None, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_READ))):
    total_result = await db.execute(select(func.count(Skill.id)))
    total = total_result.scalar()
    result = await db.execute(select(Skill).offset(skip).limit(limit))
    skills = result.scalars().all()
    if tag:
        skills = [s for s in skills if tag in (s.tags or [])]
        total = len(skills)
    return SkillListResponse(total=total, skills=await _to_read(db, skills))


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
    return (await _to_read(db, [skill]))[0]


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

    skill = await _upsert_skill(db, result["skill_data"])
    await db.commit()
    await db.refresh(skill)
    read = SkillRead.model_validate(skill)
    return SkillInstallResponse(success=True, skill=read, installed=[read])


@router.post("/skills/import", response_model=SkillInstallResponse)
async def import_skill_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SKILL_WRITE)),
):
    """Import skills from an uploaded .md, .json, or .zip skill bundle.

    A zip may carry a whole skill repository: every ``SKILL.md`` inside becomes
    one skill, and its sibling files become that skill's bundle.
    """
    from app.services.skill_installer import install_skills_from_upload

    if not file.filename:
        return SkillInstallResponse(success=False, error="No filename provided")

    content = await file.read()
    result = install_skills_from_upload(file.filename, content)
    if not result["success"]:
        return SkillInstallResponse(success=False, error=result["error"])

    installed: List[SkillRead] = []
    failed: List[SkillImportFailure] = []
    for entry in result["skills"]:
        skill_data = entry["skill_data"]
        try:
            skill = await _upsert_skill(db, skill_data, entry.get("files"))
            await db.commit()
            await db.refresh(skill)
            installed.append((await _to_read(db, [skill]))[0])
        except Exception as e:  # one bad skill must not sink the whole bundle
            await db.rollback()
            failed.append(SkillImportFailure(name=skill_data.get("name"), error=str(e)))

    if not installed:
        detail = "; ".join(f"{f.name}: {f.error}" for f in failed) or "Nothing was imported"
        return SkillInstallResponse(success=False, failed=failed, error=detail)

    return SkillInstallResponse(
        success=True,
        skill=installed[0] if len(installed) == 1 else None,
        installed=installed,
        failed=failed,
    )


@router.get("/skills/{skill_id}/files", response_model=SkillFileListResponse)
async def list_skill_files(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SKILL_READ)),
):
    """List the bundled resource files of a skill (metadata only)."""
    skill = (await db.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    rows = (
        await db.execute(
            select(SkillFile)
            .where(SkillFile.skill_id == skill_id)
            .order_by(SkillFile.path)
        )
    ).scalars().all()
    files = [
        SkillFileRead(
            path=r.path,
            size_bytes=r.size_bytes,
            mime=r.mime,
            is_binary=r.content_text is None,
        )
        for r in rows
    ]
    return SkillFileListResponse(skill_id=skill_id, total=len(files), files=files)


@router.get("/skills/{skill_id}/files/{path:path}")
async def get_skill_file(
    skill_id: int,
    path: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SKILL_READ)),
):
    """Return the content of one bundled skill file."""
    row = (
        await db.execute(
            select(SkillFile).where(
                SkillFile.skill_id == skill_id,
                SkillFile.path == path,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Skill file not found")

    payload = row.content_blob if row.content_text is None else row.content_text.encode("utf-8")
    media_type = row.mime or "application/octet-stream"
    # Bundle files are attacker-supplied content; never let a browser render them.
    return Response(
        content=payload or b"",
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{path.rsplit("/", 1)[-1]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )



@router.post("/skills/{skill_id}/promote", response_model=ToolRead,
             status_code=status.HTTP_201_CREATED)
async def promote_skill_script(
    skill_id: int,
    script_path: str,
    body: SkillScriptPromoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission(Permission.SKILL_SCRIPT_APPROVE)),
):
    """Promote one reviewed bundle script into an executable Tool.

    The script path is a query parameter rather than a route segment because a
    greedy {path:path} converter would swallow a trailing /promote.
    """
    from app.core.audit import record_action

    skill = (await db.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if (await db.execute(select(Tool).where(Tool.name == body.name))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tool name already exists")

    data = await validate_promotion(db, skill_id, script_path, body)
    tool = Tool(**data)
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    await record_action(
        user_id=current_user.user_id, action="skill.script.promote",
        action_category=data.get("action_category"), risk_tier=data.get("risk_tier"),
        human_reviewer=str(current_user.user_id),
        input_data={"skill_id": skill_id, "script_path": script_path,
                    "digest": data["source_bundle_digest"]},
        output_data={"tool_id": tool.id, "tool_name": tool.name},
    )
    return ToolRead.model_validate(tool)

# --- Tools ---
@router.get("/tools", response_model=ToolListResponse)
async def list_tools(skip: int = 0, limit: int = 50, tag: Optional[str] = None, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.SKILL_READ))):
    total_result = await db.execute(select(func.count(Tool.id)))
    total = total_result.scalar()
    result = await db.execute(select(Tool).offset(skip).limit(limit))
    tools = result.scalars().all()
    if tag:
        tools = [t for t in tools if tag in (t.tags or [])]
        total = len(tools)
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


@router.post("/tools/{tool_id}/execute")
async def execute_pool_tool(
    tool_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """Run an executable Tool with the supplied args (manual test / direct call)."""
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if not tool.command_template:
        raise HTTPException(status_code=400, detail="Tool is not executable (no command_template)")
    # ROLE_PERMISSIONS is keyed by Role enum; current_user.role is a string
    perms = {p.value for p in ROLE_PERMISSIONS.get(Role(current_user.role), [])}
    return await execute_tool(
        tool, body.get("args") or {}, user_id=current_user.user_id,
        caller_permissions=perms,
    )
