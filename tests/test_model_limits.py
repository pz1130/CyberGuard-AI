"""M0a-2: context_window / max_output_tokens catalog and remaining-budget compress."""
from unittest.mock import AsyncMock

import pytest

from agent_core.compressor import maybe_compress
from agent_core.model_limits import (
    DEFAULT_CONTEXT_WINDOW,
    enrich_model_entry,
    lookup_model_limits,
    resolve_model_limits,
)
from agent_core.tokens import remaining_budget


def test_lookup_known_models():
    cw, mo = lookup_model_limits("gpt-4o")
    assert cw == 128_000 and mo == 16_384
    cw, mo = lookup_model_limits("claude-sonnet-4-7-2025")
    assert cw == 200_000
    cw, mo = lookup_model_limits("openai/gpt-4o-mini")
    assert cw == 128_000


def test_lookup_unknown_uses_defaults():
    cw, mo = lookup_model_limits("my-custom-finetune-v3")
    assert cw == DEFAULT_CONTEXT_WINDOW
    assert mo >= 1024


def test_resolve_prefers_explicit_fields():
    models = [
        {
            "name": "gpt-4o",
            "model_type": "chat",
            "context_window": 64_000,
            "max_output_tokens": 2_000,
        }
    ]
    cw, mo = resolve_model_limits("gpt-4o", models)
    assert cw == 64_000 and mo == 2_000


def test_resolve_fills_from_catalog_when_missing_on_entry():
    models = [{"name": "gpt-4o", "model_type": "chat"}]
    cw, mo = resolve_model_limits("gpt-4o", models)
    assert cw == 128_000 and mo == 16_384


def test_enrich_model_entry_non_destructive():
    e = enrich_model_entry({"name": "gpt-4o", "context_window": 99_999})
    assert e["context_window"] == 99_999
    assert e["max_output_tokens"] == 16_384  # filled


def test_remaining_budget_math():
    assert remaining_budget(128_000, reserve_output=16_384, reserve_system=512) == (
        128_000 - 16_384 - 512
    )


@pytest.mark.asyncio
async def test_maybe_compress_uses_context_window_remaining_budget():
    """With a large context_window, short history must not compress."""
    history = [{"role": "user", "content": "hello world " * 50}]
    router = AsyncMock()
    new, compressed, degraded = await maybe_compress(
        history,
        router,
        context_window=128_000,
        reserve_output=4096,
        keep_last=6,
    )
    assert compressed is False and degraded is False
    assert new == history
    router.chat.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_compress_context_window_triggers_when_full():
    # ~20k weighted tokens of ascii (~80k chars) vs tiny remaining budget
    history = [{"role": "user", "content": "x" * 80_000}]
    router = AsyncMock()
    router.chat = AsyncMock(return_value="## Goal\nok\n## Constraints\n\n## Progress\n"
                                           "## Key Decisions\n## Next Steps\n## Critical Context\n")
    new, compressed, degraded = await maybe_compress(
        history,
        router,
        context_window=8_192,
        reserve_output=4_000,
        reserve_system=512,
        keep_last=1,
    )
    # remaining ≈ 8192-4000-512 = 3680; 80000/4 = 20000 tokens → compress
    assert compressed is True
    assert new[0]["role"] == "system"
    router.chat.assert_awaited()


def test_model_info_schema_accepts_limits():
    from app.schemas.provider import ModelInfo
    m = ModelInfo(name="gpt-4o", context_window=128000, max_output_tokens=16384)
    d = m.model_dump()
    assert d["context_window"] == 128000
    assert d["max_output_tokens"] == 16384


def test_settings_reserve_fields():
    from app.config import settings
    assert int(settings.CONTEXT_COMPRESS_RESERVE_OUTPUT) == 1024
    assert int(settings.CONTEXT_COMPRESS_RESERVE_SYSTEM) == 512
    assert int(settings.DEFAULT_CONTEXT_WINDOW) == 128000
