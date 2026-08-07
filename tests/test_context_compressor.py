"""Unit tests for app.core.context_compressor (pure-function layer)."""
from unittest.mock import AsyncMock

import pytest

from app.core.context_compressor import (
    compress_history,
    estimate_tokens,
    maybe_compress,
    select_window,
)


def test_estimate_tokens_empty():
    assert estimate_tokens([]) == 0


def test_estimate_tokens_short_string_rounds_down():
    # 3 chars // 4 == 0
    assert estimate_tokens([{"role": "user", "content": "abc"}]) == 0


def test_estimate_tokens_long_string():
    # 401 chars // 4 == 100
    assert estimate_tokens([{"role": "user", "content": "x" * 401}]) == 100


def test_estimate_tokens_cjk_counts_one_token_per_char():
    # CJK costs ~1 token per codepoint, not 4 chars/token: 4 chars -> 4 tokens.
    assert estimate_tokens([{"role": "user", "content": "你好世界"}]) == 4


def test_estimate_tokens_mixed_cjk_and_latin():
    # 2 CJK (2 tokens) + 8 latin chars (8 // 4 == 2) == 4
    assert estimate_tokens([{"role": "user", "content": "你好" + "a" * 8}]) == 4


def test_estimate_tokens_kana_and_hangul_count_as_cjk():
    assert estimate_tokens([{"role": "user", "content": "こんにちは"}]) == 5
    assert estimate_tokens([{"role": "user", "content": "안녕하세요"}]) == 5


def test_estimate_tokens_missing_content_key_coerced_to_None_string():
    # m.get("content") returns None; str(None) -> "None" (4 chars) // 4 == 1
    assert estimate_tokens([{"role": "user"}]) == 1


def test_estimate_tokens_non_string_content_coerced():
    # numeric / None / mixed types should not raise
    msgs = [
        {"role": "user", "content": 12345},
        {"role": "assistant", "content": None},
    ]
    # len("12345") // 4 == 1; len("None") // 4 == 1; total 2
    assert estimate_tokens(msgs) == 2


def test_estimate_tokens_sums_across_messages():
    msgs = [
        {"role": "user", "content": "a" * 100},        # 25
        {"role": "assistant", "content": "b" * 200},   # 50
        {"role": "user", "content": "c" * 4},          # 1
    ]
    assert estimate_tokens(msgs) == 76


# ---- select_window ----

def test_select_window_short_history_with_summary_prepends_summary():
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    out = select_window(history, "summary text", keep_last=6)
    assert out == [
        {"role": "system", "content": "summary text"},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]


def test_select_window_over_limit_with_summary_prepends():
    history = [{"role": m, "content": str(i)} for i, m in enumerate(["user", "assistant"] * 5)]
    out = select_window(history, "summary", keep_last=3)
    assert out[0] == {"role": "system", "content": "summary"}
    assert out[1:] == history[-3:]
    assert len(out) == 4


def test_select_window_over_limit_empty_summary_returns_tail_only():
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    out = select_window(history, "", keep_last=4)
    assert out == history[-4:]


def test_select_window_keep_last_zero_summary_present():
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    out = select_window(history, "sum", keep_last=0)
    assert out == [{"role": "system", "content": "sum"}]


def test_select_window_keep_last_zero_empty_summary():
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    out = select_window(history, "", keep_last=0)
    assert out == []


# ---- async orchestrators (Task 2) ----

import pytest
from unittest.mock import AsyncMock

from app.core.context_compressor import compress_history, maybe_compress


# ---- compress_history ----

@pytest.mark.asyncio
async def test_compress_history_below_threshold_no_llm_call():
    history = [{"role": "user", "content": "hi"}]
    router = AsyncMock()
    new, summary = await compress_history(history, router, max_tokens=100, keep_last=6)
    assert summary is None
    assert new == history
    router.chat.assert_not_called()


@pytest.mark.asyncio
async def test_compress_history_at_threshold_calls_llm_once():
    # 4 messages x 1000 chars = 1000 tokens, above max_tokens=100
    history = [{"role": "user", "content": "x" * 1000} for _ in range(4)]
    router = AsyncMock()
    router.chat.return_value = "  summary body  "
    new, summary = await compress_history(history, router, max_tokens=100, keep_last=3)
    assert summary == "summary body"  # stripped
    assert router.chat.await_count == 1
    assert len(new) == 1 + 3
    assert new[0] == {"role": "system", "content": "summary body"}
    assert new[1:] == history[-3:]


@pytest.mark.asyncio
async def test_compress_history_llm_raises_degrades_to_window():
    history = [{"role": "user", "content": "x" * 4000}]
    router = AsyncMock()
    router.chat.side_effect = RuntimeError("rate limit")
    new, summary = await compress_history(history, router, max_tokens=100, keep_last=2)
    assert summary is None
    assert new == history[-2:]


@pytest.mark.asyncio
async def test_compress_history_no_router_at_threshold_degrades():
    history = [{"role": "user", "content": "x" * 4000}]
    new, summary = await compress_history(history, None, max_tokens=100, keep_last=2)
    assert summary is None
    assert new == history[-2:]


# ---- maybe_compress ----

@pytest.mark.asyncio
async def test_maybe_compress_below_threshold_unchanged():
    history = [{"role": "user", "content": "x" * 100}]
    router = AsyncMock()
    new, compressed, degraded = await maybe_compress(
        history, router, max_tokens=1000, keep_last=6
    )
    assert new == history
    assert compressed is False
    assert degraded is False
    router.chat.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_compress_at_threshold_returns_compressed():
    # 5 messages x 1000 chars = 1250 tokens, above max_tokens=100
    history = [{"role": "user", "content": "x" * 1000} for _ in range(5)]
    router = AsyncMock()
    router.chat.return_value = "summary"
    new, compressed, degraded = await maybe_compress(
        history, router, max_tokens=100, keep_last=4
    )
    assert compressed is True
    assert degraded is False
    assert new[0]["content"] == "summary"
    assert len(new) == 1 + 4
    assert new[1:] == history[-4:]


@pytest.mark.asyncio
async def test_maybe_compress_llm_raises_degraded_path():
    history = [{"role": "user", "content": "x" * 4000}]
    router = AsyncMock()
    router.chat.side_effect = TimeoutError("upstream slow")
    new, compressed, degraded = await maybe_compress(
        history, router, max_tokens=100, keep_last=3
    )
    assert compressed is False
    assert degraded is True
    assert new == history[-3:]


@pytest.mark.asyncio
async def test_maybe_compress_no_router_at_threshold_degrades():
    history = [{"role": "user", "content": "x" * 4000}]
    new, compressed, degraded = await maybe_compress(
        history, None, max_tokens=100, keep_last=3
    )
    assert compressed is False
    assert degraded is True
    assert new == history[-3:]


@pytest.mark.asyncio
async def test_maybe_compress_empty_history():
    router = AsyncMock()
    new, compressed, degraded = await maybe_compress(
        [], router, max_tokens=100, keep_last=6
    )
    assert new == []
    assert compressed is False
    assert degraded is False
    router.chat.assert_not_called()


def test_settings_have_context_compress_fields():
    from app.config import settings
    # Defaults: 8000 / 6
    assert int(getattr(settings, "CONTEXT_COMPRESS_MAX_TOKENS", 8000)) == 8000
    assert int(getattr(settings, "CONTEXT_COMPRESS_KEEP_LAST", 6)) == 6
