"""Agent configuration and management router."""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_role, require_permission
from app.core.rbac import Role, Permission
from app.core.security import encrypt_data
from app.schemas.agent import (
    AgentConfigCreate, AgentConfigRead, AgentConfigUpdate,
    AgentConfigListResponse, AgentTestRequest, AgentTestResponse,
)
from app.models.agent import AgentConfig
from sqlalchemy import select

router = APIRouter()


@router.get("/agents", response_model=AgentConfigListResponse)
async def list_agents(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """List all configured sub-agents."""
    from sqlalchemy import func
    total_result = await db.execute(select(func.count(AgentConfig.id)))
    total = total_result.scalar()
    result = await db.execute(select(AgentConfig).offset(skip).limit(limit))
    agents = result.scalars().all()
    return AgentConfigListResponse(total=total, agents=[AgentConfigRead.model_validate(a) for a in agents])


@router.post("/agents", response_model=AgentConfigRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Register a new sub-agent configuration."""
    existing = await db.execute(select(AgentConfig).where(AgentConfig.agent_name == body.agent_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Agent name already exists")

    # Build metadata_json with OpenClaw fields
    metadata = dict(body.metadata_json) if body.metadata_json else {}
    if body.api_key:
        metadata["api_key"] = encrypt_data(body.api_key)
    if body.auth_mode:
        metadata["auth_mode"] = body.auth_mode
    if body.streaming is not None:
        metadata["streaming"] = body.streaming
    metadata_json = metadata if metadata else None

    agent = AgentConfig(**body.model_dump(exclude={'env_vars', 'api_key', 'auth_mode', 'streaming', 'metadata_json'}))
    agent.metadata_json = metadata_json
    # Encrypt env_vars before storing
    if body.env_vars:
        agent.env_vars_encrypted = encrypt_data(json.dumps(body.env_vars))
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentConfigRead.model_validate(agent)


@router.get("/agents/{agent_id}", response_model=AgentConfigRead)
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """Get agent configuration by ID."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentConfigRead.model_validate(agent)


@router.put("/agents/{agent_id}", response_model=AgentConfigRead)
async def update_agent(
    agent_id: int,
    body: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Update agent configuration."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "env_vars" and value:
            setattr(agent, "env_vars_encrypted", encrypt_data(json.dumps(value)))
        elif key == "api_key" and value:
            # Encrypt and store in metadata_json
            metadata = dict(agent.metadata_json) if agent.metadata_json else {}
            metadata["api_key"] = encrypt_data(value)
            agent.metadata_json = metadata
        elif key in ("auth_mode", "streaming"):
            # Store in metadata_json
            metadata = dict(agent.metadata_json) if agent.metadata_json else {}
            metadata[key] = value
            agent.metadata_json = metadata
        elif key == "metadata_json":
            # Merge with existing metadata
            existing = dict(agent.metadata_json) if agent.metadata_json else {}
            existing.update(value or {})
            agent.metadata_json = existing
        else:
            setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return AgentConfigRead.model_validate(agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_DELETE)),
):
    """Delete agent configuration."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


@router.post("/agents/{agent_id}/test", response_model=AgentTestResponse)
async def test_agent_connection(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """Test connection to a sub-agent endpoint."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from app.services.agent_executor import get_executor_for_backend
    config_dict = {
        "id": agent.id,
        "agent_name": agent.agent_name,
        "backend_type": agent.backend_type,
        "endpoint_url": agent.endpoint_url,
        "env_vars_encrypted": agent.env_vars_encrypted,
        "metadata_json": agent.metadata_json,
    }
    executor = get_executor_for_backend(config_dict)
    test_result = await executor.test_connection()
    return AgentTestResponse(**test_result)
