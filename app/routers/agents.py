"""Agent configuration and management router."""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.security import encrypt_data, decrypt_data
from app.schemas.agent import (
    AgentConfigCreate, AgentConfigRead, AgentConfigUpdate,
    AgentConfigListResponse, AgentTestResponse,
)
from app.models.agent import AgentConfig

router = APIRouter()


def _build_metadata(body_dict: dict, existing: dict | None = None) -> dict:
    """Merge OpenClaw fields into metadata_json.

    Fields stored in metadata_json:
      - openclaw_agent_id: the Clawith Agent UUID (for x-openclaw-agent-id header)
      - api_key_encrypted: AES-256 encrypted API key
    """
    meta = dict(existing or {})

    # Clawith Agent ID
    if "openclaw_agent_id" in body_dict:
        val = body_dict.pop("openclaw_agent_id")
        if val:
            meta["openclaw_agent_id"] = val

    # API key — encrypt before storing
    if "api_key" in body_dict:
        raw_key = body_dict.pop("api_key") or ""
        if raw_key and raw_key != "******":
            meta["api_key_encrypted"] = encrypt_data(raw_key)

    return meta


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/agents", response_model=AgentConfigListResponse)
async def list_agents(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """List all configured sub-agents."""
    total = (await db.execute(select(func.count(AgentConfig.id)))).scalar()
    rows = (await db.execute(select(AgentConfig).offset(skip).limit(limit))).scalars().all()
    return AgentConfigListResponse(total=total, agents=[AgentConfigRead.model_validate(a) for a in rows])


@router.post("/agents", response_model=AgentConfigRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Register a new sub-agent configuration.

    For OpenClaw (Clawith) agents, set:
      - backend_type = "openclaw"
      - endpoint_url = your Clawith base URL  (e.g. http://clawith:18789)
      - openclaw_agent_id = the Agent UUID from Clawith
      - api_key = your Clawith API key  (stored AES-256 encrypted)
    """
    existing = await db.execute(select(AgentConfig).where(AgentConfig.agent_name == body.agent_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Agent name already exists")

    body_dict = body.model_dump()
    metadata = _build_metadata(body_dict, existing=body_dict.pop("metadata_json", None))

    # Encrypt env_vars if provided
    env_vars = body_dict.pop("env_vars", None)
    env_vars_encrypted = encrypt_data(json.dumps(env_vars)) if env_vars else None

    agent = AgentConfig(
        **{k: v for k, v in body_dict.items() if hasattr(AgentConfig, k)},
        metadata_json=metadata or None,
        env_vars_encrypted=env_vars_encrypted,
    )
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
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    body_dict = body.model_dump(exclude_unset=True)

    # Handle OpenClaw-specific fields → metadata_json
    metadata_update = {}
    for field in ("openclaw_agent_id", "api_key"):
        if field in body_dict:
            metadata_update[field] = body_dict.pop(field)
    if metadata_update:
        existing_meta = dict(agent.metadata_json or {})
        merged = _build_metadata(metadata_update, existing=existing_meta)
        agent.metadata_json = merged

    # Handle env_vars
    if "env_vars" in body_dict:
        env_vars = body_dict.pop("env_vars")
        agent.env_vars_encrypted = encrypt_data(json.dumps(env_vars)) if env_vars else None

    # Regular fields
    for key, value in body_dict.items():
        if hasattr(agent, key):
            setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return AgentConfigRead.model_validate(agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

@router.post("/agents/{agent_id}/test", response_model=AgentTestResponse)
async def test_agent_connection(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """Send a minimal test request to verify the agent is reachable."""
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    endpoint = agent.endpoint_url or ""
    if not endpoint:
        return AgentTestResponse(success=False, error="No endpoint URL configured")

    if agent.backend_type == "openclaw":
        from app.services import openclaw_executor
        from app.services.agent_executor import _resolve_api_key

        config_dict = {
            "env_vars_encrypted": agent.env_vars_encrypted,
            "metadata_json": agent.metadata_json or {},
        }
        api_key = _resolve_api_key(config_dict)
        meta = agent.metadata_json or {}
        openclaw_agent_id = meta.get("openclaw_agent_id") or meta.get("agent_id") or "main"

        test_result = await openclaw_executor.test_connection(
            endpoint_url=endpoint,
            api_key=api_key,
            openclaw_agent_id=openclaw_agent_id,
        )
    else:
        # Generic HTTP ping for Hermes / custom backends
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{endpoint.rstrip('/')}/health")
            test_result = {"success": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            test_result = {"success": False, "error": str(e)}

    return AgentTestResponse(**test_result)


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

@router.post("/agents/{agent_id}/execute")
async def execute_agent(
    agent_id: int,
    body: dict,
    _=Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """Manually trigger a task on a specific sub-agent."""
    from app.services.agent_executor import AgentExecutor
    task = body.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="'task' field is required")
    result = await AgentExecutor().execute(agent_id=agent_id, task=task, user_id=0)
    return result
