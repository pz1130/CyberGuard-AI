"""Unit tests for app.core.context_compressor (pure-function layer)."""
from app.core.context_compressor import estimate_tokens, select_window


def test_estimate_tokens_empty():
    assert estimate_tokens([]) == 0


def test_estimate_tokens_short_string_rounds_down():
    # 3 chars // 4 == 0
    assert estimate_tokens([{"role": "user", "content": "abc"}]) == 0


def test_estimate_tokens_long_string():
    # 401 chars // 4 == 100
    assert estimate_tokens([{"role": "user", "content": "x" * 401}]) == 100


def test_estimate_tokens_cjk_is_chars_not_bytes():
    # 4 CJK chars // 4 == 1
    assert estimate_tokens([{"role": "user", "content": "你好世界"}]) == 1


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
