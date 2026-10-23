"""Tests for provider verification status stamping + seed behavior."""
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.provider import Provider
from app.routers.providers import (
    _stamp_model_verified, _seed_presets, _PRESET_PROVIDERS,
    _test_provider_connectivity,
)


pytestmark = pytest.mark.asyncio


async def test_minimax_preset_includes_native_embedding_model():
    minimax_presets = [p for p in _PRESET_PROVIDERS if p.name.startswith("MiniMax")]
    assert {(p.name, p.base_url) for p in minimax_presets} == {
        ("MiniMax 国内版", "https://api.minimax.cn/v1"),
        ("MiniMax 海外版", "https://api.minimax.io/v1"),
    }
    for minimax in minimax_presets:
        models = [(m.name, m.model_type) for m in minimax.models]
        assert ("embo-01", "embedding") in models
        assert any(name.startswith("MiniMax") and mtype == "chat" for name, mtype in models)


async def test_openai_preset_includes_embedding_models():
    openai = next(p for p in _PRESET_PROVIDERS if p.name == "OpenAI")
    types = {m.name: m.model_type for m in openai.models}
    assert types.get("text-embedding-3-small") == "embedding"
    assert types.get("gpt-4o") == "chat"


async def test_stamp_updates_existing_model():
    existing = [
        {"name": "a", "model_type": "chat"},
        {"name": "b", "model_type": "chat", "verified": False, "test_error": "old"},
    ]
    out = _stamp_model_verified(existing, "a", ok=True)
    assert out[0]["name"] == "a"
    assert out[0]["verified"] is True
    assert out[0]["last_tested_at"]  # ISO string, truthy
    assert out[0].get("test_error") is None
    # Unrelated model untouched (no verified/test_error/last_tested_at added)
    assert out[1] == {"name": "b", "model_type": "chat", "verified": False, "test_error": "old"}
    # Original list not mutated (regression guard for SQLAlchemy change detection)
    assert "verified" not in existing[0]


async def test_stamp_appends_unknown_model():
    existing = [{"name": "a", "model_type": "chat"}]
    out = _stamp_model_verified(existing, "c", ok=False, err="HTTP 401")
    assert len(out) == 2
    assert out[1]["name"] == "c"
    assert out[1]["model_type"] == "chat"
    assert out[1]["verified"] is False
    assert out[1]["test_error"] == "HTTP 401"
    assert out[1]["last_tested_at"]


async def test_stamp_truncates_long_error():
    existing = [{"name": "a"}]
    long_err = "x" * 500
    out = _stamp_model_verified(existing, "a", ok=False, err=long_err)
    assert len(out[0]["test_error"]) == 200


async def test_stamp_tolerates_legacy_string_models():
    """Older rows may have a stray string in models (e.g. 'gpt-4o')."""
    existing = ["gpt-4o", {"name": "b"}]
    out = _stamp_model_verified(existing, "b", ok=True)
    assert out[0] == {"name": "gpt-4o", "model_type": "chat"}  # string → dict
    assert out[1]["name"] == "b"
    assert out[1]["verified"] is True


async def test_stamp_tolerates_none_input():
    out = _stamp_model_verified(None, "x", ok=True)
    assert len(out) == 1
    assert out[0]["name"] == "x"
    assert out[0]["verified"] is True
    assert out[0]["model_type"] == "chat"


async def test_seed_presets_leaves_models_unverified():
    """Built-in presets are NOT pre-verified. The Chat page dropdown only
    shows models the user has actually tested via /providers/test or
    /providers/{id}/models/probe. Until then, every preset model's
    `verified` must stay None (= untested) — the user must click TEST in
    the Providers page for each one they want to use.

    This is the inverse of the original design (which pre-stamped
    verified=True on the assumption that presets were 'tested by hand').
    Most presets are unfilled placeholders (no API key, wrong base_url,
    local services not running), so claiming they're verified would
    lie to the user.
    """
    from sqlalchemy import delete

    async with AsyncSessionLocal() as db:
        # Isolate from polluted local DB rows (older seed stamped verified=True).
        preset_names = {p.name for p in _PRESET_PROVIDERS}
        await db.execute(delete(Provider).where(Provider.name.in_(preset_names)))
        await db.commit()
        await _seed_presets(db)
        result = await db.execute(select(Provider).where(Provider.name.in_(preset_names)))
        providers = result.scalars().all()
        assert len(providers) == len(preset_names)
        for p in providers:
            assert p.models, f"{p.name} has no models"
            for m in p.models:
                assert isinstance(m, dict)
                assert m.get("verified") is None, (
                    f"{p.name}/{m.get('name')}: preset was pre-verified — "
                    f"this means the Chat dropdown will lie about which models work"
                )
                assert m.get("last_tested_at") is None
                assert m.get("test_error") is None
        minimax_rows = [p for p in providers if p.name.startswith("MiniMax")]
        assert len(minimax_rows) == 2
        for minimax in minimax_rows:
            embo = next((m for m in minimax.models if m.get("name") == "embo-01"), None)
            assert embo is not None, "MiniMax preset must include native embedding model embo-01"
            assert embo.get("model_type") == "embedding"


async def test_seed_migrates_legacy_minimax_without_losing_credentials():
    """The old one-size-fits-all preset becomes the China preset in place."""
    from sqlalchemy import delete
    from app.core.security import CredentialField, encrypt_data

    minimax_names = ["MiniMax", "MiniMax 国内版", "MiniMax 海外版"]
    encrypted_key = encrypt_data("domestic-key", CredentialField.PROVIDER_API_KEY)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Provider).where(Provider.name.in_(minimax_names)))
        legacy = Provider(
            name="MiniMax",
            provider_type="openai",
            base_url="https://api.minimax.cn/anthropic",
            api_key_encrypted=encrypted_key,
            models=[{"name": "MiniMax-M3", "model_type": "chat", "verified": True}],
            is_active=True,
        )
        db.add(legacy)
        await db.commit()
        await db.refresh(legacy)
        legacy_id = legacy.id

        await _seed_presets(db)
        result = await db.execute(
            select(Provider).where(Provider.name.in_(minimax_names)).order_by(Provider.name)
        )
        rows = result.scalars().all()

        assert {row.name for row in rows} == {"MiniMax 国内版", "MiniMax 海外版"}
        domestic = next(row for row in rows if row.name == "MiniMax 国内版")
        assert domestic.id == legacy_id
        assert domestic.base_url == "https://api.minimax.cn/v1"
        assert domestic.api_key_encrypted == encrypted_key
        assert any(m.get("name") == "MiniMax-M3" and m.get("verified") is True for m in domestic.models)

        await db.execute(delete(Provider).where(Provider.name.in_(minimax_names)))
        await db.commit()


async def test_stamp_then_reload_roundtrip():
    """Full round-trip: create a provider, stamp a model, commit, reload,
    verify the value persisted. Guards against SQLAlchemy not detecting
    the JSON-column mutation."""
    tag = f"stamp-test-{utc_now().timestamp()}"
    p = Provider(
        name=tag,
        provider_type="openai",
        base_url="https://example.com/v1",
        models=[{"name": "m1", "model_type": "chat"}],
        is_active=True,
    )
    async with AsyncSessionLocal() as session:
        session.add(p)
        await session.commit()
        await session.refresh(p)
        pid = p.id

    try:
        # Re-fetch and stamp
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Provider).where(Provider.id == pid))
            prov = result.scalar_one()
            prov.models = _stamp_model_verified(prov.models, "m1", ok=True)
            await session.commit()
        # Re-fetch and assert
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Provider).where(Provider.id == pid))
            prov = result.scalar_one()
            assert prov.models[0]["verified"] is True
            assert prov.models[0]["last_tested_at"]
    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Provider).where(Provider.name == tag))
            for prov in result.scalars().all():
                await session.delete(prov)
            await session.commit()


async def test_connectivity_401_is_failure(monkeypatch):
    import httpx
    from openai import APIStatusError
    from unittest.mock import AsyncMock, MagicMock

    response = httpx.Response(
        401,
        request=httpx.Request("POST", "https://provider.example/v1/chat/completions"),
    )
    error = APIStatusError("Unauthorized", response=response, body=None)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=error)
    monkeypatch.setattr("app.routers.providers.AsyncOpenAI", lambda **_kwargs: client)

    result = await _test_provider_connectivity(
        base_url="https://provider.example/v1",
        api_key="bad-key",
        provider_type="openai",
        api_version=None,
        models=[{"name": "chat-model", "model_type": "chat"}],
    )

    assert result.success is False
    assert "401" in (result.error or "")
