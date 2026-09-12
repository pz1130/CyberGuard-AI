"""Master Agent configuration router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.services.master_config import get_master_config, update_master_config
from app.models.provider import Provider


class MasterConfigResponse(BaseModel):
    id: int
    provider_id: Optional[int] = Field(
        default=None,
        validation_alias='llm_provider_id',
        serialization_alias='provider_id',
    )
    model: str = Field(validation_alias='llm_model', serialization_alias='model')
    temperature: float
    system_prompt: str
    intent_parser_prompt: str
    summarizer_prompt: str
    max_rounds: int
    auto_approve_threshold: int
    # Branding
    branding_logo: Optional[str] = None
    branding_company_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MasterConfigUpdate(BaseModel):
    provider_id: Optional[int] = None
    model: Optional[str] = Field(default=None, validation_alias='model', serialization_alias='model')
    temperature: Optional[float] = None
    system_prompt: Optional[str] = None
    intent_parser_prompt: Optional[str] = None
    summarizer_prompt: Optional[str] = None
    max_rounds: Optional[int] = None
    auto_approve_threshold: Optional[int] = None
    # Branding
    branding_logo: Optional[str] = None
    branding_company_name: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class BrandingPublic(BaseModel):
    """Public subset for header/login display (no auth)."""
    branding_logo: Optional[str] = None
    branding_company_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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
    current = await get_master_config(db)
    update_data = body.model_dump(exclude_unset=True)
    selected_provider_id = update_data.get('provider_id', current.llm_provider_id)
    selected_model = update_data.get('model', current.llm_model)
    selection_supplied = 'provider_id' in update_data or 'model' in update_data
    if selection_supplied:
        if not selected_provider_id or not selected_model:
            raise HTTPException(
                status_code=400,
                detail="Master Agent provider and model must be selected together",
            )
        result = await db.execute(
            select(Provider).where(
                Provider.id == selected_provider_id,
                Provider.is_active.is_(True),
            )
        )
        provider = result.scalar_one_or_none()
        if provider is None:
            raise HTTPException(status_code=400, detail="Selected provider is not active")
        model_names = {
            model.get("name") if isinstance(model, dict) else str(model)
            for model in (provider.models or [])
            if not isinstance(model, dict) or model.get("model_type", "chat") == "chat"
        }
        if selected_model not in model_names:
            raise HTTPException(
                status_code=400,
                detail="Selected model does not belong to the selected provider",
            )
        if not provider.api_key_encrypted:
            raise HTTPException(
                status_code=400,
                detail="Selected provider has no configured API key",
            )

    if 'provider_id' in update_data:
        update_data['llm_provider_id'] = update_data.pop('provider_id')
    if 'model' in update_data:
        update_data['llm_model'] = update_data.pop('model')
    config = await update_master_config(db, update_data)
    await invalidate_cache()
    # Also invalidate the llm_router's cached config
    from app.services.llm_router import get_llm_router
    get_llm_router().invalidate_master_config_cache()
    return MasterConfigResponse.model_validate(config)


@router.get("/branding", response_model=BrandingPublic)
async def get_branding_public(
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint for branding (logo + company name). No authentication required."""
    config = await get_master_config(db)
    return BrandingPublic.model_validate(config)
