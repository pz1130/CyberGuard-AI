"""Environment variable management router."""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.security import encrypt_data, decrypt_data
from app.models.envvar import EnvVar
from app.schemas.envvar import EnvVarCreate, EnvVarUpdate, EnvVarRead, EnvVarListResponse

router = APIRouter()


@router.get("/envvars", response_model=EnvVarListResponse)
async def list_envvars(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    """List all env vars. Values are NEVER returned."""
    total_result = await db.execute(select(func.count(EnvVar.id)))
    total = total_result.scalar()
    result = await db.execute(select(EnvVar).offset(skip).limit(limit))
    vars_ = result.scalars().all()
    return EnvVarListResponse(total=total, vars=[EnvVarRead.model_validate(v) for v in vars_])


@router.post("/envvars", response_model=EnvVarRead, status_code=status.HTTP_201_CREATED)
async def create_envvar(
    body: EnvVarCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Create a new env var. Encrypts value before storing."""
    existing = await db.execute(select(EnvVar).where(EnvVar.key == body.key))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Env var '{body.key}' already exists")

    encrypted_value = encrypt_data(body.value)
    env_var = EnvVar(
        key=body.key,
        value_encrypted=encrypted_value,
        value_type=body.value_type,
        description=body.description,
        is_active=body.is_active,
    )
    db.add(env_var)
    await db.commit()
    await db.refresh(env_var)
    return EnvVarRead.model_validate(env_var)


@router.put("/envvars/{var_id}", response_model=EnvVarRead)
async def update_envvar(
    var_id: int,
    body: EnvVarUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Update an env var. Re-encrypts value if changed."""
    result = await db.execute(select(EnvVar).where(EnvVar.id == var_id))
    env_var = result.scalar_one_or_none()
    if not env_var:
        raise HTTPException(status_code=404, detail="Env var not found")

    if body.value is not None:
        env_var.value_encrypted = encrypt_data(body.value)
    if body.value_type is not None:
        env_var.value_type = body.value_type
    if body.description is not None:
        env_var.description = body.description
    if body.is_active is not None:
        env_var.is_active = body.is_active

    await db.commit()
    await db.refresh(env_var)
    return EnvVarRead.model_validate(env_var)


@router.delete("/envvars/{var_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_envvar(
    var_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Delete an env var."""
    result = await db.execute(select(EnvVar).where(EnvVar.id == var_id))
    env_var = result.scalar_one_or_none()
    if not env_var:
        raise HTTPException(status_code=404, detail="Env var not found")
    await db.delete(env_var)
    await db.commit()


@router.get("/envvars/decrypt/{var_id}")
async def decrypt_envvar(
    var_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """
    Decrypt and return the plaintext value of an env var.
    Only available to admins with SETTINGS_WRITE permission.
    """
    result = await db.execute(select(EnvVar).where(EnvVar.id == var_id))
    env_var = result.scalar_one_or_none()
    if not env_var:
        raise HTTPException(status_code=404, detail="Env var not found")
    plaintext = decrypt_data(env_var.value_encrypted)
    return {"id": env_var.id, "key": env_var.key, "value": plaintext}


@router.post("/envvars/resolve")
async def resolve_envvars(
    keys: list[str],
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    """
    Decrypt a list of env vars by key. Used internally by AgentExecutor
    and MCP subprocess startup — not exposed to the UI.
    Returns a dict of key → plaintext value.
    """
    result = await db.execute(
        select(EnvVar).where(EnvVar.key.in_(keys), EnvVar.is_active == True)
    )
    vars_ = result.scalars().all()
    return {v.key: decrypt_data(v.value_encrypted) for v in vars_}
