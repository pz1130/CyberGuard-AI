"""Master Agent configuration router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.services.master_config import get_master_config, update_master_config


class MasterConfigResponse(BaseModel):
    id: int
    model: str
    temperature: float
    system_prompt: str
    intent_parser_prompt: str
    summarizer_prompt: str
    max_rounds: int
    auto_approve_threshold: int

    model_config = ConfigDict(from_attributes=True)


class MasterConfigUpdate(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    system_prompt: Optional[str] = None
    intent_parser_prompt: Optional[str] = None
    summarizer_prompt: Optional[str] = None
    max_rounds: Optional[int] = None
    auto_approve_threshold: Optional[int] = None


router = APIRouter()


@router.get("/master-config", response_model=MasterConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    """Get master agent configuration."""
    config = await get_master_config(db)
    return MasterConfigResponse.model_validate(config)


@router.put("/master-config", response_model=MasterConfigResponse)
async def put_config(
    body: MasterConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Update master agent configuration."""
    from app.services.master_config import invalidate_cache
    update_data = body.model_dump(exclude_unset=True)
    config = await update_master_config(db, update_data)
    await invalidate_cache()
    # Also invalidate the llm_router's cached config
    from app.services.llm_router import get_llm_router
    get_llm_router().invalidate_master_config_cache()
    return MasterConfigResponse.model_validate(config)