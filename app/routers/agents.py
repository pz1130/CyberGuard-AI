"""Agent configuration and management router."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_role, require_permission
from app.core.rbac import Role, Permission
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

    agent = AgentConfig(**body.model_dump(exclude={'env_vars'}))
    # Encrypt env_vars before storing
    if body.env_vars:
        from app.core.security import encrypt_data
        import json
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

    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "env_vars" and value:
            from app.core.security import encrypt_data
            import json
            setattr(agent, "env_vars_encrypted", encrypt_data(json.dumps(value)))
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

    from app.services.agent_executor import SubAgentWrapper
    config_dict = {
        "id": agent.id,
        "agent_name": agent.agent_name,
        "backend_type": agent.backend_type,
        "endpoint_url": agent.endpoint_url,
        "env_vars_encrypted": agent.env_vars_encrypted,
    }
    wrapper = SubAgentWrapper(config_dict)
    test_result = await wrapper.test_connection()
    return AgentTestResponse(**test_result)
