"""N8N connection and workflow management router."""
import httpx
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.security import encrypt_data, decrypt_data
from app.models.n8n import N8NConnection
from app.services.n8n_service import (
    test_connection as test_n8n_connection,
    list_workflows as fetch_n8n_workflows,
    get_workflow as fetch_n8n_workflow,
    create_workflow as create_n8n_workflow,
    update_workflow as update_n8n_workflow,
    delete_workflow as delete_n8n_workflow,
    generate_workflow_json,
)
from app.services.llm_router import LLMRouter


router = APIRouter()


# Pydantic schemas
class N8NConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    base_url: str = Field(..., description="N8N instance URL, e.g. https://n8n.example.com")
    api_key: Optional[str] = None
    is_active: bool = True
    is_default: bool = False


class N8NConnectionUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class N8NConnectionResponse(BaseModel):
    id: int
    name: str
    base_url: str
    api_key: Optional[str] = None
    is_active: bool
    is_default: bool
    metadata_json: Optional[dict] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class N8NTestResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    workflow_count: Optional[int] = None


class WorkflowGenerateRequest(BaseModel):
    description: str = Field(..., description="Natural language description of the workflow")
    connection_id: Optional[int] = Field(None, description="N8N connection ID to use")


class WorkflowGenerateResponse(BaseModel):
    workflow_json: dict
    description: str
    raw_llm_response: Optional[str] = None


class WorkflowSummary(BaseModel):
    id: str
    name: str
    active: bool
    nodes_count: int = 0
    tags: List[str] = []


def _decrypt_api_key(encrypted: Optional[str]) -> Optional[str]:
    if not encrypted:
        return None
    try:
        return decrypt_data(encrypted)
    except Exception:
        return None


def _connection_to_response(conn: N8NConnection) -> N8NConnectionResponse:
    api_key_masked = "******" if conn.api_key_encrypted else None
    return N8NConnectionResponse(
        id=conn.id,
        name=conn.name,
        base_url=conn.base_url,
        api_key=api_key_masked,
        is_active=conn.is_active,
        is_default=conn.is_default,
        metadata_json=conn.metadata_json,
        created_at=conn.created_at.isoformat(),
        updated_at=conn.updated_at.isoformat(),
    )


@router.get("/n8n/connections", response_model=List[N8NConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """List all N8N connections."""
    result = await db.execute(select(N8NConnection))
    connections = result.scalars().all()
    return [_connection_to_response(c) for c in connections]


@router.post("/n8n/connections", response_model=N8NConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    body: N8NConnectionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Register a new N8N connection."""
    if body.is_default:
        # Unset default on other connections
        await db.execute(
            select(N8NConnection).where(N8NConnection.is_default == True)
        )
        for conn in (await db.execute(select(N8NConnection).where(N8NConnection.is_default == True))).scalars():
            conn.is_default = False

    connection = N8NConnection(
        name=body.name,
        base_url=body.base_url,
        api_key_encrypted=encrypt_data(body.api_key) if body.api_key else None,
        is_active=body.is_active,
        is_default=body.is_default,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return _connection_to_response(connection)


@router.get("/n8n/connections/{connection_id}", response_model=N8NConnectionResponse)
async def get_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """Get N8N connection by ID."""
    result = await db.execute(select(N8NConnection).where(N8NConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return _connection_to_response(conn)


@router.put("/n8n/connections/{connection_id}", response_model=N8NConnectionResponse)
async def update_connection(
    connection_id: int,
    body: N8NConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Update N8N connection."""
    result = await db.execute(select(N8NConnection).where(N8NConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if body.is_default and not conn.is_default:
        # Unset default on other connections
        for other in (await db.execute(select(N8NConnection).where(N8NConnection.is_default == True))).scalars():
            other.is_default = False

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "api_key":
            if value and value != "******":
                setattr(conn, "api_key_encrypted", encrypt_data(value))
        else:
            setattr(conn, key, value)

    await db.commit()
    await db.refresh(conn)
    return _connection_to_response(conn)


@router.delete("/n8n/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Delete N8N connection."""
    result = await db.execute(select(N8NConnection).where(N8NConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()


@router.post("/n8n/connections/{connection_id}/test", response_model=N8NTestResponse)
async def test_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Test N8N connection."""
    result = await db.execute(select(N8NConnection).where(N8NConnection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    api_key = _decrypt_api_key(conn.api_key_encrypted)
    result = await test_n8n_connection(conn.base_url, api_key or "")
    return N8NTestResponse(
        success=result.get("success", False),
        error=result.get("error"),
        workflow_count=result.get("workflow_count"),
    )


async def _get_default_connection(db: AsyncSession) -> Optional[N8NConnection]:
    """Get the default N8N connection."""
    result = await db.execute(
        select(N8NConnection).where(N8NConnection.is_default == True, N8NConnection.is_active == True)
    )
    return result.scalar_one_or_none()


async def _get_connection_or_default(db: AsyncSession, connection_id: Optional[int]) -> Optional[N8NConnection]:
    """Get connection by ID or return default."""
    if connection_id:
        result = await db.execute(select(N8NConnection).where(N8NConnection.id == connection_id))
        return result.scalar_one_or_none()
    return await _get_default_connection(db)


@router.get("/n8n/workflows")
async def list_workflows(
    connection_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """List workflows from N8N instance."""
    conn = await _get_connection_or_default(db, connection_id)
    if not conn:
        raise HTTPException(status_code=400, detail="No N8N connection configured. Add one in N8N settings.")

    api_key = _decrypt_api_key(conn.api_key_encrypted)
    workflows = await fetch_n8n_workflows(conn.base_url, api_key or "")

    return [
        WorkflowSummary(
            id=w.get("id", ""),
            name=w.get("name", "Untitled"),
            active=w.get("active", False),
            nodes_count=len(w.get("nodes", [])),
            tags=w.get("tags", []),
        )
        for w in workflows
    ]


@router.get("/n8n/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    connection_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """Get a specific workflow from N8N."""
    conn = await _get_connection_or_default(db, connection_id)
    if not conn:
        raise HTTPException(status_code=400, detail="No N8N connection configured")

    api_key = _decrypt_api_key(conn.api_key_encrypted)
    workflow = await fetch_n8n_workflow(conn.base_url, api_key or "", workflow_id)
    return workflow


@router.post("/n8n/workflows/generate", response_model=WorkflowGenerateResponse)
async def generate_workflow(
    body: WorkflowGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Generate N8N workflow JSON using AI."""
    llm_router = LLMRouter()
    result = await generate_workflow_json(body.description, llm_router)
    return WorkflowGenerateResponse(
        workflow_json=result.get("workflow_json", {}),
        description=body.description,
        raw_llm_response=result.get("raw_llm_response"),
    )


@router.post("/n8n/workflows", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    name: str,
    workflow_json: dict,
    connection_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Create a new workflow in N8N."""
    conn = await _get_connection_or_default(db, connection_id)
    if not conn:
        raise HTTPException(status_code=400, detail="No N8N connection configured")

    api_key = _decrypt_api_key(conn.api_key_encrypted)
    workflow_data = {**workflow_json, "name": name, "active": False}
    result = await create_n8n_workflow(conn.base_url, api_key or "", workflow_data)
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "active": result.get("active", False),
        "nodes_count": len(result.get("nodes", [])),
    }


@router.put("/n8n/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    workflow_json: dict,
    connection_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Update an existing workflow in N8N."""
    conn = await _get_connection_or_default(db, connection_id)
    if not conn:
        raise HTTPException(status_code=400, detail="No N8N connection configured")

    api_key = _decrypt_api_key(conn.api_key_encrypted)
    result = await update_n8n_workflow(conn.base_url, api_key or "", workflow_id, workflow_json)
    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "active": result.get("active", False),
        "nodes_count": len(result.get("nodes", [])),
    }


@router.delete("/n8n/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    connection_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Delete a workflow from N8N."""
    conn = await _get_connection_or_default(db, connection_id)
    if not conn:
        raise HTTPException(status_code=400, detail="No N8N connection configured")

    api_key = _decrypt_api_key(conn.api_key_encrypted)
    await delete_n8n_workflow(conn.base_url, api_key or "", workflow_id)
