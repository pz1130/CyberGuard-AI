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
from app.core.security import CredentialField, encrypt_data, decrypt_data
from app.core.time import utc_now
from app.models.provider import Provider
from app.schemas.provider import (
    ModelInfo,
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
    MINIMAX = "minimax"
    CUSTOM = "custom"


router = APIRouter()

_PRESET_PROVIDERS: list[ProviderCreate] = [
    ProviderCreate(
        name="OpenAI",
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key="",
        models=[
            ModelInfo(name="gpt-4o", model_type="chat"),
            ModelInfo(name="gpt-4o-mini", model_type="chat"),
            ModelInfo(name="gpt-4-turbo", model_type="chat"),
            ModelInfo(name="gpt-3.5-turbo", model_type="chat"),
            ModelInfo(name="text-embedding-3-small", model_type="embedding"),
            ModelInfo(name="text-embedding-3-large", model_type="embedding"),
        ],
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
        models=[
            ModelInfo(name="Qwen/Qwen2.5-7B-Instruct", model_type="chat"),
            ModelInfo(name="deepseek-ai/DeepSeek-V2.5", model_type="chat"),
            ModelInfo(name="BAAI/bge-m3", model_type="embedding"),
        ],
    ),
    ProviderCreate(
        name="Zhipu AI (智谱)",
        provider_type="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="",
        models=[
            ModelInfo(name="glm-4-flash", model_type="chat"),
            ModelInfo(name="glm-4-plus", model_type="chat"),
            ModelInfo(name="glm-3-turbo", model_type="chat"),
            ModelInfo(name="embedding-3", model_type="embedding"),
        ],
    ),
    # Bailian (阿里云百炼) — OpenAI-compatible endpoint for Qwen / 通义千问 series.
    # Docs: https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
    # Beijing: https://dashscope.aliyuncs.com/compatible-mode/v1
    # Intl (US): https://dashscope-us.aliyuncs.com/compatible-mode/v1
    # Get key from https://bailian.console.aliyun.com/ (DASHSCOPE_API_KEY)
    ProviderCreate(
        name="Bailian (阿里云百炼)",
        provider_type="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="",
        models=[
            ModelInfo(name="qwen-max", model_type="chat"),
            ModelInfo(name="qwen-plus", model_type="chat"),
            ModelInfo(name="qwen-turbo", model_type="chat"),
            ModelInfo(name="qwen-long", model_type="chat"),
            ModelInfo(name="qwq-plus", model_type="chat"),
            ModelInfo(name="deepseek-r1", model_type="chat"),
            ModelInfo(name="text-embedding-v3", model_type="embedding"),
        ],
    ),
    # MiniMax — the China and international platforms issue region-specific keys,
    # so expose both OpenAI-compatible endpoints instead of asking users to edit
    # one ambiguous preset. The domains come from MiniMax's regional SDK docs.
    # Embeddings are NOT OpenAI-compatible: use native embo-01 ({texts, type}
    # body, vectors in the response). LLMRouter.embed() routes MiniMax hosts
    # through that adapter.
    ProviderCreate(
        name="MiniMax 国内版",
        provider_type="openai",
        base_url="https://api.minimax.cn/v1",
        api_key="",
        models=[
            ModelInfo(name="MiniMax-M3", model_type="chat"),
            ModelInfo(name="MiniMax-M2.7", model_type="chat"),
            ModelInfo(name="MiniMax-M2.5", model_type="chat"),
            ModelInfo(name="MiniMax-M2.1", model_type="chat"),
            ModelInfo(name="MiniMax-M2", model_type="chat"),
            ModelInfo(name="MiniMax-Text-01", model_type="chat"),
            ModelInfo(name="embo-01", model_type="embedding"),
        ],
    ),
    ProviderCreate(
        name="MiniMax 海外版",
        provider_type="openai",
        base_url="https://api.minimax.io/v1",
        api_key="",
        models=[
            ModelInfo(name="MiniMax-M3", model_type="chat"),
            ModelInfo(name="MiniMax-M2.7", model_type="chat"),
            ModelInfo(name="MiniMax-M2.5", model_type="chat"),
            ModelInfo(name="MiniMax-M2.1", model_type="chat"),
            ModelInfo(name="MiniMax-M2", model_type="chat"),
            ModelInfo(name="MiniMax-Text-01", model_type="chat"),
            ModelInfo(name="embo-01", model_type="embedding"),
        ],
    ),
    # All of the below speak the OpenAI wire protocol via their /v1 (or Gemini's
    # OpenAI-compat) endpoint, so they slot into the unified AsyncOpenAI client.
    # Endpoints verified reachable 2026-06-03; refine model lists via auto-discover.
    ProviderCreate(
        name="Google Gemini",
        provider_type="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="",
        models=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    ),
    ProviderCreate(
        name="DeepSeek",
        provider_type="openai",
        base_url="https://api.deepseek.com/v1",
        api_key="",
        models=["deepseek-chat", "deepseek-reasoner"],
    ),
    ProviderCreate(
        name="Moonshot (Kimi)",
        provider_type="openai",
        base_url="https://api.moonshot.cn/v1",
        api_key="",
        models=["kimi-latest", "moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"],
    ),
    ProviderCreate(
        name="xAI (Grok)",
        provider_type="openai",
        base_url="https://api.x.ai/v1",
        api_key="",
        models=["grok-4", "grok-3", "grok-2-vision-latest"],
    ),
    ProviderCreate(
        name="LM Studio (Local)",
        provider_type="openai",
        base_url="http://localhost:1234/v1",
        api_key="lm-studio",
        models=["local-model"],
    ),
]


def _normalize_provider_models(
    models,
    *,
    base_url: Optional[str],
    name: Optional[str],
    provider_type: Optional[str],
) -> list:
    """Validate embedding types and backfill MiniMax embo-01."""
    from app.services.embedding_catalog import (
        classify_model_type,
        ensure_provider_embedding_models,
        validate_embedding_models,
    )

    as_dicts: list = []
    for m in models or []:
        if isinstance(m, dict):
            as_dicts.append(dict(m))
        elif hasattr(m, "model_dump"):
            as_dicts.append(m.model_dump())
        else:
            as_dicts.append({"name": str(m), "model_type": "chat"})
    for entry in as_dicts:
        if not entry.get("model_type"):
            entry["model_type"] = classify_model_type(entry.get("name"))
    validate_embedding_models(
        as_dicts, base_url=base_url, name=name, provider_type=provider_type,
    )
    return ensure_provider_embedding_models(
        as_dicts, base_url=base_url, name=name, provider_type=provider_type,
    )


def _model_type_of(models: list, model_name: str) -> str:
    from app.services.embedding_catalog import classify_model_type
    for m in models or []:
        if isinstance(m, dict) and m.get("name") == model_name:
            return m.get("model_type") or classify_model_type(model_name)
        if getattr(m, "name", None) == model_name:
            return getattr(m, "model_type", None) or classify_model_type(model_name)
    return classify_model_type(model_name)


async def _seed_presets(db: AsyncSession):
    """Seed preset providers (idempotent — only seeds if name doesn't exist).

    Commits per-preset and tolerates the unique-name race that occurs when several
    API workers run the startup seed concurrently: a duplicate-name insert just means
    another worker already seeded that preset, which is benign.

    **Presets are NOT pre-stamped `verified=True`.** Most built-in presets are
    placeholders the user hasn't actually configured (no API key, wrong base_url,
    Ollama not running locally, etc.); declaring them "verified" without a real
    chat-completions round-trip would lie to the user and show broken models in
    the Chat page dropdown. The verified flag stays `None` (= untested) until
    the user explicitly hits TEST or PROBE on the Providers page.
    """
    from sqlalchemy.exc import IntegrityError

    # Migrate the former single MiniMax preset in place so an existing API key,
    # model verification state and provider id are preserved. Older releases
    # also used api.minimaxi.com; MiniMax's current China OpenAI SDK docs use
    # api.minimax.cn instead.
    legacy_result = await db.execute(select(Provider).where(Provider.name == "MiniMax"))
    legacy = legacy_result.scalar_one_or_none()
    if legacy is not None:
        is_international = "api.minimax.io" in (legacy.base_url or "").lower()
        target_name = "MiniMax 海外版" if is_international else "MiniMax 国内版"
        target_url = "https://api.minimax.io/v1" if is_international else "https://api.minimax.cn/v1"
        target_result = await db.execute(select(Provider).where(Provider.name == target_name))
        if target_result.scalar_one_or_none() is None:
            legacy.name = target_name
            legacy.base_url = target_url
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()

    # Also repair built-in regional presets that still point at the retired
    # China host or an Anthropic path. Non-MiniMax custom hosts are untouched.
    domestic_result = await db.execute(
        select(Provider).where(Provider.name == "MiniMax 国内版")
    )
    domestic = domestic_result.scalar_one_or_none()
    domestic_host = (domestic.base_url or "").lower() if domestic is not None else ""
    if domestic is not None and (
        "api.minimaxi.com" in domestic_host or "api.minimax.cn" in domestic_host
    ) and domestic.base_url != "https://api.minimax.cn/v1":
        domestic.base_url = "https://api.minimax.cn/v1"
        await db.commit()

    international_result = await db.execute(
        select(Provider).where(Provider.name == "MiniMax 海外版")
    )
    international = international_result.scalar_one_or_none()
    international_host = (
        (international.base_url or "").lower() if international is not None else ""
    )
    if (
        international is not None
        and "api.minimax.io" in international_host
        and international.base_url != "https://api.minimax.io/v1"
    ):
        international.base_url = "https://api.minimax.io/v1"
        await db.commit()

    for preset in _PRESET_PROVIDERS:
        existing = await db.execute(select(Provider).where(Provider.name == preset.name))
        if existing.scalar_one_or_none():
            continue
        # Store as JSON-serializable dicts; the column can't hold ModelInfo objects.
        # `verified` / `last_tested_at` / `test_error` are left unset — only a real
        # test/probe call (which routes through `_stamp_model_verified`) can fill them.
        # context_window / max_output_tokens filled from catalog when absent (M0a-2).
        from app.services.model_limits import enrich_models_list
        provider = Provider(
            name=preset.name,
            provider_type=preset.provider_type,
            api_key_encrypted=encrypt_data(preset.api_key, CredentialField.PROVIDER_API_KEY) if preset.api_key else None,
            base_url=preset.base_url,
            api_version=preset.api_version,
            models=enrich_models_list(_normalize_provider_models(
                [m.model_dump() for m in preset.models],
                base_url=preset.base_url,
                name=preset.name,
                provider_type=preset.provider_type,
            )),
            is_active=preset.is_active,
            metadata_json=preset.metadata_json,
        )
        db.add(provider)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()  # another worker seeded this preset first

    # Existing MiniMax rows were seeded chat-only. Backfill embo-01 so knowledge
    # ingest can select a real embedding model without a manual re-add.
    from app.services.embedding_catalog import (
        ensure_provider_embedding_models,
        is_minimax_provider,
    )
    result = await db.execute(select(Provider))
    for row in result.scalars().all():
        if not is_minimax_provider(row.base_url, row.name, row.provider_type):
            continue
        has_embo = any(
            isinstance(m, dict) and m.get("name") == "embo-01" and m.get("model_type") == "embedding"
            for m in (row.models or [])
        )
        if has_embo:
            continue
        row.models = ensure_provider_embedding_models(
            row.models, base_url=row.base_url, name=row.name, provider_type=row.provider_type,
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()


async def _test_provider_connectivity(
    base_url: str,
    api_key: str,
    provider_type: str,
    api_version: Optional[str],
    models: list,
    test_model: Optional[str] = None,
    metadata_json: Optional[dict] = None,
) -> ProviderTestResponse:
    """Ping the provider with a minimal completion or embedding call."""
    if not base_url:
        return ProviderTestResponse(
            success=False,
            error="base_url is required",
        )

    # Resolve model name: explicit test_model > first chat model in list > fallback
    if test_model:
        model_name = test_model
    elif models:
        first = models[0]
        # Stored models are {"name": ..., "model_type": ...} dicts; may also be a
        # ModelInfo object or a legacy plain string. Extract just the name.
        if isinstance(first, dict):
            model_name = first.get("name") or "gpt-4o-mini"
        else:
            model_name = getattr(first, "name", None) or str(first)
    else:
        model_name = "gpt-4o-mini"

    extra_kwargs: dict = {"api_key": api_key or "dummy"}
    if provider_type == "azure":
        extra_kwargs["api_version"] = api_version or "2024-02-01"

    client = AsyncOpenAI(base_url=base_url.rstrip("/"), **extra_kwargs)

    start = time.monotonic()
    try:
        if _model_type_of(models, model_name) == "embedding":
            from app.services.embedding_catalog import is_minimax_provider
            if is_minimax_provider(base_url):
                from app.services.minimax_embedder import embed_texts
                meta = metadata_json or {}
                vectors, _usage = await embed_texts(
                    ["ping"],
                    api_key=api_key or "",
                    base_url=base_url,
                    model=model_name,
                    group_id=str(meta.get("group_id") or meta.get("GroupId") or "") or None,
                    embed_type="query",
                )
                if not vectors or not vectors[0]:
                    raise ValueError("No embedding data received")
            else:
                resp = await client.embeddings.create(model=model_name, input=["ping"])
                if not getattr(resp, "data", None):
                    raise ValueError("No embedding data received")
            latency_ms = (time.monotonic() - start) * 1000
            return ProviderTestResponse(
                success=True,
                latency_ms=round(latency_ms, 1),
                model=model_name,
            )

        # MiniMax uses OpenAI-compatible API despite anthropic provider_type
        if provider_type == "anthropic" and ("minimaxi" in base_url or ".minimaxi.com" in base_url):
            minimax_model = "MiniMax-Text-01"
            try:
                await client.chat.completions.create(
                    model=minimax_model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=5,
                )
                latency_ms = (time.monotonic() - start) * 1000
                return ProviderTestResponse(
                    success=True,
                    latency_ms=round(latency_ms, 1),
                    model=minimax_model,
                )
            except APIStatusError as e:
                latency_ms = (time.monotonic() - start) * 1000
                if e.status_code == 401:
                    return ProviderTestResponse(
                        success=False,
                        latency_ms=round(latency_ms, 1),
                        model=minimax_model,
                        error="HTTP 401: Unauthorized — check your API key",
                    )
                return ProviderTestResponse(
                    success=False,
                    latency_ms=round(latency_ms, 1),
                    model=minimax_model,
                    error=f"HTTP {e.status_code}: {e.message[:200]}",
                )
            except Exception as e:
                latency_ms = (time.monotonic() - start) * 1000
                return ProviderTestResponse(
                    success=False,
                    latency_ms=round(latency_ms, 1),
                    model=minimax_model,
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
                "model": model_name,
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
                        model=model_name,
                        error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    )
        else:
            await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
        latency_ms = (time.monotonic() - start) * 1000
        return ProviderTestResponse(
            success=True,
            latency_ms=round(latency_ms, 1),
            model=model_name,
        )
    except APIStatusError as e:
        latency_ms = (time.monotonic() - start) * 1000
        if e.status_code == 401:
            return ProviderTestResponse(
                success=False,
                latency_ms=round(latency_ms, 1),
                model=model_name,
                error="HTTP 401: Unauthorized — check your API key",
            )
        return ProviderTestResponse(
            success=False,
            latency_ms=round(latency_ms, 1),
            model=model_name,
            error=f"HTTP {e.status_code}: {e.message[:200]}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return ProviderTestResponse(
            success=False,
            latency_ms=round(latency_ms, 1),
            model=model_name,
            error=str(e)[:200],
        )


def _stamp_model_verified(
    models: Optional[list],
    model_name: str,
    ok: bool,
    err: Optional[str] = None,
) -> list:
    """Return a new models list with `model_name`'s verification status updated.

    - If a dict with this name already exists, update its `verified`,
      `last_tested_at`, and (on failure) `test_error` in place.
    - If no such dict exists (e.g. a freshly discovered model), append a stub
      chat-model entry with the verification status.

    The list is replaced (not mutated) so SQLAlchemy detects the JSON change
    when the caller assigns the result back to `provider.models = ...`.
    Also fills context_window / max_output_tokens when missing (M0a-2 catalog).
    """
    from app.services.model_limits import enrich_model_entry

    result: list = [dict(m) if isinstance(m, dict) else {"name": str(m), "model_type": "chat"}
                    for m in (models or [])]
    now_iso = utc_now().isoformat()
    for entry in result:
        if entry.get("name") == model_name:
            entry["verified"] = bool(ok)
            entry["last_tested_at"] = now_iso
            entry["test_error"] = (err or "")[:200] if not ok else None
            # Fill limits only on the model we just stamped (leave siblings untouched).
            if entry.get("model_type", "chat") == "chat":
                entry.update(enrich_model_entry(entry))
            return result
    # Not found — append a stub with catalog limits
    result.append(enrich_model_entry({
        "name": model_name,
        "model_type": "chat",
        "verified": bool(ok),
        "last_tested_at": now_iso,
        "test_error": (err or "")[:200] if not ok else None,
    }))
    return result


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

    # SSRF protection — validate base_url before saving
    if body.base_url:
        from app.core.ssrf import validate_outbound_url, SSRFError
        try:
            validate_outbound_url(body.base_url)
        except SSRFError as e:
            raise HTTPException(status_code=400, detail=f"Invalid base_url: {e}")

    from app.services.model_limits import enrich_models_list
    try:
        models = _normalize_provider_models(
            [m.model_dump() for m in body.models],
            base_url=body.base_url,
            name=body.name,
            provider_type=body.provider_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    provider = Provider(
        name=body.name,
        provider_type=body.provider_type,
        api_key_encrypted=encrypt_data(body.api_key, CredentialField.PROVIDER_API_KEY) if body.api_key else None,
        base_url=body.base_url,
        api_version=body.api_version,
        # Store as JSON-serializable dicts; the column can't hold ModelInfo objects.
        models=enrich_models_list(models),
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
    """Test connectivity to an AI provider, persisting the per-model verified flag."""
    result = await db.execute(select(Provider).where(Provider.id == body.provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = None
    if provider.api_key_encrypted:
        try:
            api_key = decrypt_data(provider.api_key_encrypted, CredentialField.PROVIDER_API_KEY)
        except Exception:
            api_key = None

    test_resp = await _test_provider_connectivity(
        base_url=provider.base_url or "",
        api_key=api_key or "",
        provider_type=provider.provider_type,
        api_version=provider.api_version,
        models=provider.models or [],
        test_model=body.test_model,
        metadata_json=provider.metadata_json or {},
    )

    # Stamp per-model verified flag using the model that was actually tested.
    tested_model = test_resp.model
    if tested_model:
        provider.models = _stamp_model_verified(
            provider.models,
            tested_model,
            ok=test_resp.success,
            err=test_resp.error,
        )
        try:
            await db.commit()
            await db.refresh(provider)
        except Exception:
            await db.rollback()
            # Don't fail the test endpoint — the connectivity result is the
            # primary response, the stamp is best-effort.

    return test_resp


@router.get("/providers/{provider_id}/models/discover")
async def discover_provider_models(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Discover available models by querying the provider's GET /models endpoint.

    Runs server-side with the stored (decrypted) API key, so it works for saved
    providers whose key is masked in API responses, and avoids browser CORS to the
    provider. Returns ``{"models": [{"name": ..., "model_type": "chat"}, ...]}``.
    """
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.base_url:
        raise HTTPException(status_code=400, detail="Provider has no base_url configured")

    from app.core.ssrf import validate_outbound_url, SSRFError
    try:
        validate_outbound_url(provider.base_url)
    except SSRFError as e:
        raise HTTPException(status_code=400, detail=f"Invalid base_url: {e}")

    api_key = None
    if provider.api_key_encrypted:
        try:
            api_key = decrypt_data(provider.api_key_encrypted, CredentialField.PROVIDER_API_KEY)
        except Exception:
            api_key = None

    url = provider.base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach provider: {e}")
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Provider returned {resp.status_code}: {resp.text[:200]}",
        )

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Provider /models did not return JSON")

    # Accept both OpenAI ({data:[{id}]}) and {models:[{name|id}]} shapes.
    ids: list[str] = []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        ids = [m.get("id") for m in data["data"] if isinstance(m, dict) and m.get("id")]
    elif isinstance(data, dict) and isinstance(data.get("models"), list):
        ids = [
            (m.get("name") or m.get("id")) if isinstance(m, dict) else str(m)
            for m in data["models"]
        ]
        ids = [m for m in ids if m]
    if not ids:
        raise HTTPException(status_code=404, detail="Provider returned no models")

    from app.services.model_limits import enrich_model_entry
    from app.services.embedding_catalog import classify_model_type, ensure_provider_embedding_models
    discovered = [
        enrich_model_entry({"name": name, "model_type": classify_model_type(name)})
        for name in ids
    ]
    return {
        "models": ensure_provider_embedding_models(
            discovered,
            base_url=provider.base_url,
            name=provider.name,
            provider_type=provider.provider_type,
        )
    }


@router.post("/providers/{provider_id}/models/probe")
async def probe_provider_capabilities(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Probe every model on the provider for tools/vision support, cache the
    result inline on each model (``models[i].capabilities``), and stamp a
    successful probe as ``verified=True``. On-demand only.
    """
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    models = provider.models or []
    if not models:
        raise HTTPException(status_code=400, detail="Provider has no models to probe")

    from app.services.llm_router import get_llm_router
    from app.services.capability_prober import probe_model
    from app.services.embedding_catalog import looks_like_embedding_model, looks_like_rerank_model

    client = await get_llm_router().get_client_async(provider_id=provider_id)

    from app.services.model_limits import enrich_model_entry
    from datetime import datetime, timezone

    updated = []
    for m in models:
        # Models are stored as dicts, but tolerate a stray legacy string.
        entry = dict(m) if isinstance(m, dict) else {"name": str(m), "model_type": "chat"}
        name = entry.get("name")
        model_type = entry.get("model_type") or "chat"
        if name and (model_type == "embedding" or looks_like_embedding_model(name)):
            try:
                vecs = await get_llm_router().embed(
                    ["ping"], model=name, provider_id=provider_id, embed_type="query",
                )
                entry["verified"] = bool(vecs and vecs[0])
                entry["last_tested_at"] = datetime.now(timezone.utc).isoformat()
                if entry["verified"]:
                    entry.pop("test_error", None)
                else:
                    entry["test_error"] = "No embedding data received"
            except Exception as e:  # noqa: BLE001
                entry["verified"] = False
                entry["test_error"] = str(e)[:200]
            updated.append(entry)
            continue
        if name and (model_type == "rerank" or looks_like_rerank_model(name)):
            # Rerank is not probed here; skip chat-completions to avoid 400s.
            updated.append(entry)
            continue
        if name:
            try:
                cap = await probe_model(client, name)
                entry["capabilities"] = cap
                # Probe used the same chat-completions call as the connectivity
                # test, so a successful probe means the model is reachable.
                entry["verified"] = True
                entry["last_tested_at"] = cap.get("probed_at") or entry.get("last_tested_at")
                # Clear any stale failure from a prior probe/test on this model
                entry.pop("test_error", None)
            except Exception as e:  # noqa: BLE001 - one bad model shouldn't abort the batch
                entry["verified"] = False
                entry["test_error"] = str(e)[:200]
        if entry.get("model_type", "chat") == "chat":
            entry = enrich_model_entry(entry)
        updated.append(entry)

    # Reassign (not in-place mutate) so SQLAlchemy detects the JSON change.
    provider.models = updated
    await db.commit()
    get_llm_router().invalidate_provider_cache(provider_id)
    return {"models": updated}


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

    # SSRF protection — validate base_url if being updated
    if "base_url" in update_data and update_data["base_url"]:
        from app.core.ssrf import validate_outbound_url, SSRFError
        try:
            validate_outbound_url(update_data["base_url"])
        except SSRFError as e:
            raise HTTPException(status_code=400, detail=f"Invalid base_url: {e}")

    if "models" in update_data:
        from app.services.model_limits import enrich_models_list
        try:
            update_data["models"] = enrich_models_list(_normalize_provider_models(
                update_data["models"],
                base_url=update_data.get("base_url") or provider.base_url,
                name=update_data.get("name") or provider.name,
                provider_type=update_data.get("provider_type") or provider.provider_type,
            ))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        from app.services.embedding_catalog import (
            ensure_provider_embedding_models,
            is_minimax_provider,
        )
        if is_minimax_provider(
            update_data.get("base_url") or provider.base_url,
            update_data.get("name") or provider.name,
            update_data.get("provider_type") or provider.provider_type,
        ):
            provider.models = ensure_provider_embedding_models(
                provider.models,
                base_url=update_data.get("base_url") or provider.base_url,
                name=update_data.get("name") or provider.name,
                provider_type=update_data.get("provider_type") or provider.provider_type,
            )

    for key, value in update_data.items():
        if key == "api_key":
            # Skip re-encryption if the client sends back the masked placeholder
            if value and value != "******":
                setattr(provider, "api_key_encrypted", encrypt_data(value, CredentialField.PROVIDER_API_KEY))
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
