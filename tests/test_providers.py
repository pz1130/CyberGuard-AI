"""Tests for provider verification status stamping + seed behavior."""
import pytest
from datetime import datetime
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.provider import Provider
from app.routers.providers import _stamp_model_verified, _seed_presets, _PRESET_PROVIDERS


pytestmark = pytest.mark.asyncio


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


async def test_stamp_then_reload_roundtrip():
    """Full round-trip: create a provider, stamp a model, commit, reload,
    verify the value persisted. Guards against SQLAlchemy not detecting
    the JSON-column mutation."""
    tag = f"stamp-test-{datetime.utcnow().timestamp()}"
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
