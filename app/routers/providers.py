"""AI Provider configuration router."""
import time
from enum import Enum
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI, APIStatusError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.security import encrypt_data, decrypt_data
from app.models.provider import Provider
from app.schemas.provider import (
    ProviderCreate,
    ProviderRead,
    ProviderUpdate,
    ProviderListResponse,
    ProviderTestRequest,
    ProviderTestResponse,
)


class ProviderType(str, Enum):
    """Supported AI provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    CUSTOM = "custom"


router = APIRouter()

_PRESET_PROVIDERS: list[ProviderCreate] = [
    ProviderCreate(
        name="OpenAI",
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key="",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    ),
    ProviderCreate(
        name="Anthropic",
        provider_type="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key="",
        models=["claude-sonnet-4-7-2025", "claude-opus-4-7-2025", "claude-haiku-3-5-2025"],
    ),
    ProviderCreate(
        name="Azure OpenAI",
        provider_type="azure",
        base_url="",
        api_key="",
        api_version="2024-02-01",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    ),
    ProviderCreate(
        name="Groq",
        provider_type="openai",
        base_url="https://api.groq.com/openai/v1",
        api_key="",
        models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    ),
    ProviderCreate(
        name="OpenRouter",
        provider_type="openai",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        models=["openai/gpt-4o", "anthropic/claude-sonnet-4-7-2025", "google/gemini-2.0-flash"],
    ),
    ProviderCreate(
        name="Ollama (Local)",
        provider_type="openai",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        models=["llama3.2", "qwen2.5", "deepseek-r1"],
    ),
    ProviderCreate(
        name="SiliconFlow",
        provider_type="openai",
        base_url="https://api.siliconflow.cn/v1",
        api_key="",
        models=["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V2.5"],
    ),
    ProviderCreate(
        name="Zhipu AI (智谱)",
        provider_type="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="",
        models=["glm-4-flash", "glm-4-plus", "glm-3-turbo"],
    ),
]


async def _seed_presets(db: AsyncSession):
    """Seed preset providers (idempotent — only seeds if name doesn't exist)."""
    for preset in _PRESET_PROVIDERS:
        existing = await db.execute(select(Provider).where(Provider.name == preset.name))
        if existing.scalar_one_or_none():
            continue
        provider = Provider(
            name=preset.name,
            provider_type=preset.provider_type,
            api_key_encrypted=encrypt_data(preset.api_key) if preset.api_key else None,
            base_url=preset.base_url,
            api_version=preset.api_version,
            models=preset.models,
            is_active=preset.is_active,
            metadata_json=preset.metadata_json,
        )
        db.add(provider)
    await db.commit()


async def _test_provider_connectivity(
    base_url: str,
    api_key: str,
    provider_type: str,
    api_version: Optional[str],
    models: list[str],
) -> ProviderTestResponse:
    """Ping the provider with a minimal completion call to validate configuration."""
    if not base_url:
        return ProviderTestResponse(
            success=False,
            error="base_url is required",
        )

    test_model = models[0] if models else "gpt-4o-mini"

    extra_kwargs: dict = {"api_key": api_key or "dummy"}
    if provider_type == "azure":
        extra_kwargs["api_version"] = api_version or "2024-02-01"

    client = AsyncOpenAI(base_url=base_url.rstrip("/"), **extra_kwargs)

    start = time.monotonic()
    try:
        # MiniMax uses OpenAI-compatible API despite anthropic provider_type
        if provider_type == "anthropic" and ("minimaxi" in base_url or ".minimaxi.com" in base_url):
            test_model = models[0] if models else "MiniMax-Text-01"
            try:
                await client.chat.completions.create(
                    model=test_model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=5,
                )
                latency_ms = (time.monotonic() - start) * 1000
                return ProviderTestResponse(
                    success=True,
                    latency_ms=round(latency_ms, 1),
                    model=test_model,
                )
            except APIStatusError as e:
                latency_ms = (time.monotonic() - start) * 1000
                if e.status_code == 401:
                    return ProviderTestResponse(
                        success=True,
                        latency_ms=round(latency_ms, 1),
                        model=test_model,
                        error="Connected (401 Unauthorized — check your API key)",
                    )
                return ProviderTestResponse(
                    success=False,
                    latency_ms=round(latency_ms, 1),
                    error=f"HTTP {e.status_code}: {e.message[:200]}",
                )
            except Exception as e:
                latency_ms = (time.monotonic() - start) * 1000
                return ProviderTestResponse(
                    success=False,
                    latency_ms=round(latency_ms, 1),
                    error=str(e)[:200],
                )

        if provider_type == "anthropic":
            import httpx
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": test_model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}],
            }
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(
                    f"{base_url.rstrip('/')}/messages",
                    headers=headers,
                    json=payload,
                )
                latency_ms = (time.monotonic() - start) * 1000
                if resp.status_code != 200:
                    return ProviderTestResponse(
                        success=False,
                        latency_ms=latency_ms,
                        error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    )
        else:
            await client.chat.completions.create(
                model=test_model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
        latency_ms = (time.monotonic() - start) * 1000
        return ProviderTestResponse(
            success=True,
            latency_ms=round(latency_ms, 1),
            model=test_model,
        )
    except APIStatusError as e:
        latency_ms = (time.monotonic() - start) * 1000
        if e.status_code == 401:
            return ProviderTestResponse(
                success=True,
                latency_ms=round(latency_ms, 1),
                model=test_model,
                error="Connected (401 Unauthorized — check your API key)",
            )
        return ProviderTestResponse(
            success=False,
            latency_ms=round(latency_ms, 1),
            error=f"HTTP {e.status_code}: {e.message[:200]}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return ProviderTestResponse(
            success=False,
            latency_ms=round(latency_ms, 1),
            error=str(e)[:200],
        )


def _provider_to_read_schema(provider: Provider) -> ProviderRead:
    """Convert Provider model to ProviderRead schema, masking api_key for security."""
    # Never return decrypted api_key in responses; mask it for display purposes
    api_key_masked = None
    if provider.api_key_encrypted:
        api_key_masked = "******"  # Masked, not the actual value

    return ProviderRead(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        api_version=provider.api_version,
        models=provider.models or [],
        is_active=provider.is_active,
        metadata_json=provider.metadata_json,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
        api_key=api_key_masked,
    )


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """List all configured AI providers."""
    total_result = await db.execute(select(func.count(Provider.id)))
    total = total_result.scalar()
    result = await db.execute(select(Provider).offset(skip).limit(limit))
    providers = result.scalars().all()
    return ProviderListResponse(
        total=total,
        providers=[_provider_to_read_schema(p) for p in providers],
    )


@router.post("/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Register a new AI provider."""
    existing = await db.execute(select(Provider).where(Provider.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider name already exists")

    provider = Provider(
        name=body.name,
        provider_type=body.provider_type,
        api_key_encrypted=encrypt_data(body.api_key) if body.api_key else None,
        base_url=body.base_url,
        api_version=body.api_version,
        models=body.models,
        is_active=body.is_active,
        metadata_json=body.metadata_json,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _provider_to_read_schema(provider)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_provider_connection(
    body: ProviderTestRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Test connectivity to an AI provider."""
    result = await db.execute(select(Provider).where(Provider.id == body.provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = None
    if provider.api_key_encrypted:
        try:
            api_key = decrypt_data(provider.api_key_encrypted)
        except Exception:
            api_key = None

    return await _test_provider_connectivity(
        base_url=provider.base_url or "",
        api_key=api_key or "",
        provider_type=provider.provider_type,
        api_version=provider.api_version,
        models=provider.models or [],
    )


@router.get("/providers/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """Get provider configuration."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _provider_to_read_schema(provider)


@router.put("/providers/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Update provider configuration."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "api_key":
            # Skip re-encryption if the client sends back the masked placeholder
            if value and value != "******":
                setattr(provider, "api_key_encrypted", encrypt_data(value))
            # If value is None or "******", keep the existing encrypted key unchanged
        else:
            setattr(provider, key, value)

    await db.commit()
    await db.refresh(provider)

    # Evict stale cached client so the next request picks up new credentials
    from app.services.llm_router import get_llm_router
    get_llm_router().invalidate_provider_cache(provider_id)

    return _provider_to_read_schema(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Delete provider."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(provider)
    await db.commit()

    from app.services.llm_router import get_llm_router
    get_llm_router().invalidate_provider_cache(provider_id)


async def seed_providers_on_startup():
    """Called by main.py lifespan to seed preset providers."""
    from app.core.database import get_db_context
    async with get_db_context() as session:
        await _seed_presets(session)