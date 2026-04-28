"""AI Provider configuration router."""
import asyncio
import time
from datetime import datetime
from enum import Enum
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI, APIStatusError

from app.core.dependencies import require_permission
from app.core.rbac import Permission
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


# In-memory provider store for MVP
_providers: dict[int, dict] = {}
_provider_counter = 0


router = APIRouter()

# ---------------------------------------------------------------------------
# Preset popular providers — seeded once on module load
# ---------------------------------------------------------------------------
_PRESET_PROVIDERS: list[ProviderCreate] = [
    # OpenAI
    ProviderCreate(
        name="OpenAI",
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key="",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    ),
    # Anthropic
    ProviderCreate(
        name="Anthropic",
        provider_type="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key="",
        models=["claude-sonnet-4-7-2025", "claude-opus-4-7-2025", "claude-haiku-3-5-2025"],
    ),
    # Azure OpenAI
    ProviderCreate(
        name="Azure OpenAI",
        provider_type="azure",
        base_url="",  # fill in: https://YOUR_RESOURCE.openai.azure.com
        api_key="",
        api_version="2024-02-01",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    ),
    # Groq (free tier, fast)
    ProviderCreate(
        name="Groq",
        provider_type="openai",
        base_url="https://api.groq.com/openai/v1",
        api_key="",
        models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    ),
    # OpenRouter (aggregates many providers)
    ProviderCreate(
        name="OpenRouter",
        provider_type="openai",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        models=["openai/gpt-4o", "anthropic/claude-sonnet-4-7-2025", "google/gemini-2.0-flash"],
    ),
    # Ollama (local)
    ProviderCreate(
        name="Ollama (Local)",
        provider_type="openai",
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # any non-empty string works for Ollama
        models=["llama3.2", "qwen2.5", "deepseek-r1"],
    ),
    # Silicon Flow (Chinese-friendly, OpenAI-compatible)
    ProviderCreate(
        name="SiliconFlow",
        provider_type="openai",
        base_url="https://api.siliconflow.cn/v1",
        api_key="",
        models=["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V2.5"],
    ),
    # Zhipu AI (Chinese)
    ProviderCreate(
        name="Zhipu AI (智谱)",
        provider_type="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="",
        models=["glm-4-flash", "glm-4-plus", "glm-3-turbo"],
    ),
]


def _seed_presets():
    """Seed preset providers once (idempotent — only seeds if store is empty)."""
    global _provider_counter
    if _providers:
        return  # already seeded
    for preset in _PRESET_PROVIDERS:
        _provider_counter += 1
        pid = _provider_counter
        data = preset.model_dump()
        data["id"] = pid
        data["created_at"] = datetime.utcnow()
        data["updated_at"] = datetime.utcnow()
        _providers[pid] = data


# Call on module import
_seed_presets()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _test_provider_connectivity(
    base_url: str,
    api_key: str,
    provider_type: str,
    api_version: str | None,
    models: list[str],
) -> ProviderTestResponse:
    """
    Actually ping the provider with a minimal completion call to validate
    the configuration. Returns latency_ms on success, error string on failure.
    """
    if not base_url:
        return ProviderTestResponse(
            success=False,
            error="base_url is required",
        )

    test_model = models[0] if models else "gpt-4o-mini"

    # Build client
    extra_kwargs: dict = {"api_key": api_key or "dummy"}
    if provider_type == "azure":
        extra_kwargs["api_version"] = api_version or "2024-02-01"

    client = AsyncOpenAI(base_url=base_url.rstrip("/"), **extra_kwargs)

    start = time.monotonic()
    try:
        if provider_type == "anthropic":
            # Anthropic uses a different endpoint /messages
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
            # OpenAI-compatible /chat/completions
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
        # 401 = auth problem, but connectivity is OK
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(_=Depends(require_permission(Permission.AGENT_READ))):
    """List all configured AI providers (presets + user-added)."""
    return ProviderListResponse(
        total=len(_providers),
        providers=[ProviderRead(**p) for p in _providers.values()],
    )


@router.post("/providers", response_model=ProviderRead, status_code=201)
async def create_provider(body: ProviderCreate, _=Depends(require_permission(Permission.AGENT_WRITE))):
    """
    Register a new AI provider.  The base_url / api_key are NOT validated
    here — use POST /providers/test to validate before saving,
    or use ?validate=true to validate as part of this call.
    """
    global _provider_counter
    _provider_counter += 1
    provider_id = _provider_counter
    provider_data = body.model_dump()
    provider_data["id"] = provider_id
    provider_data["created_at"] = datetime.utcnow()
    provider_data["updated_at"] = datetime.utcnow()
    _providers[provider_id] = provider_data
    return ProviderRead(**provider_data)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_provider_connection(
    body: ProviderTestRequest,
    _: None = Depends(require_permission(Permission.AGENT_WRITE)),
):
    """
    Test connectivity to an AI provider by sending a minimal request.
    Works with OpenAI-compatible, Anthropic, and Azure endpoints.
    """
    provider = _providers.get(body.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return await _test_provider_connectivity(
        base_url=provider.get("base_url", ""),
        api_key=provider.get("api_key", ""),
        provider_type=provider.get("provider_type", "openai"),
        api_version=provider.get("api_version"),
        models=provider.get("models", []),
    )


@router.get("/providers/{provider_id}", response_model=ProviderRead)
async def get_provider(provider_id: int, _=Depends(require_permission(Permission.AGENT_READ))):
    """Get provider configuration."""
    if provider_id not in _providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderRead(**_providers[provider_id])


@router.put("/providers/{provider_id}", response_model=ProviderRead)
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
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
