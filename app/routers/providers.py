"""AI Provider configuration router."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import require_permission
from app.core.rbac import Permission
from app.schemas.provider import ProviderCreate, ProviderRead, ProviderUpdate, ProviderListResponse

router = APIRouter()

# In-memory provider store for MVP
_providers = {}
_provider_counter = 0


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(_=Depends(require_permission(Permission.AGENT_READ))):
    """List all configured AI providers."""
    return ProviderListResponse(total=len(_providers), providers=list(_providers.values()))


@router.post("/providers", response_model=ProviderRead, status_code=201)
async def create_provider(body: ProviderCreate, _=Depends(require_permission(Permission.AGENT_WRITE))):
    """Register a new AI provider (OpenAI-compatible, Anthropic, etc.)."""
    global _provider_counter
    _provider_counter += 1
    provider_id = _provider_counter
    provider_data = body.model_dump()
    provider_data["id"] = provider_id
    provider_data["created_at"] = datetime.utcnow()
    provider_data["updated_at"] = datetime.utcnow()
    _providers[provider_id] = provider_data
    return ProviderRead(**provider_data)


@router.get("/providers/{provider_id}", response_model=ProviderRead)
async def get_provider(provider_id: int, _=Depends(require_permission(Permission.AGENT_READ))):
    """Get provider configuration."""
    if provider_id not in _providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderRead(**_providers[provider_id])


@router.put("/providers/{provider_id}", response_model=ProviderRead)
async def update_provider(provider_id: int, body: ProviderUpdate, _=Depends(require_permission(Permission.AGENT_WRITE))):
    """Update provider configuration."""
    if provider_id not in _providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    _providers[provider_id]["updated_at"] = datetime.utcnow()
    for key, value in body.model_dump(exclude_unset=True).items():
        _providers[provider_id][key] = value
    return ProviderRead(**_providers[provider_id])


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: int, _=Depends(require_permission(Permission.AGENT_WRITE))):
    """Delete provider."""
    if provider_id not in _providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    del _providers[provider_id]
