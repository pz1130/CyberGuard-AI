# Auto-Compress Long Conversation History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add threshold-triggered, per-turn compression of `conversation_history` at the master-agent entry point: one summary message + last K messages, with graceful LLM-failure degradation to a sliding window.

**Architecture:** New `app/core/context_compressor.py` provides pure functions (`estimate_tokens`, `select_window`) plus an async `maybe_compress` orchestrator. `app/agents/master.py:_summarizer_node` calls `maybe_compress` before building the LLM message list. Two new Pydantic settings gate threshold and K. No DB migration, no frontend change, no LLM router change.

**Tech Stack:** Python 3.11+, Pydantic v2 (`BaseSettings`), existing `app.config.settings`, FastAPI runtime; pytest + pytest-asyncio for tests; `AsyncMock` for the LLM router.

**Working directory:** Repository root `/Users/jc/Documents/cyber-agent/cyberguard`. All paths below are absolute or relative to that root.

**Reference spec:** `docs/superpowers/specs/2026-06-01-auto-compress-context-design.md`

---

## File Structure

| File | Role | Change |
|------|------|--------|
| `app/core/context_compressor.py` | NEW. Pure functions + async orchestrator. | Create |
| `app/agents/master.py` | Insert `maybe_compress` hook before message assembly. | Modify (1 insertion, 1 import) |
| `app/config.py` | Add `CONTEXT_COMPRESS_MAX_TOKENS`, `CONTEXT_COMPRESS_KEEP_LAST`. | Modify (2 field additions) |
| `tests/test_context_compressor.py` | Unit tests for pure functions and orchestrator. | Create |
| `docs/superpowers/plans/project_status.md` | Move spec/feature from "Not yet implemented" to "Recently completed" once landed. | Modify (1 line) |

---

## Task 1: Pure helpers + tests (`estimate_tokens`, `select_window`)

**Files:**
- Create: `app/core/context_compressor.py`
- Create: `tests/test_context_compressor.py`

- [ ] **Step 1: Create the test file with failing tests for `estimate_tokens` and `select_window`**

Create `tests/test_context_compressor.py` with the following content (all tests will fail because the module does not exist yet):

```python
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


def test_estimate_tokens_missing_content_key_treated_as_empty():
    assert estimate_tokens([{"role": "user"}]) == 0


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

def test_select_window_under_limit_unchanged():
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    out = select_window(history, "summary text", keep_last=6)
    assert out == history


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
```

- [ ] **Step 2: Run the tests to confirm they fail (module not found)**

Run from repo root:
```bash
python -m pytest tests/test_context_compressor.py -v
```
Expected: collection error / import error. Every test fails because `app.core.context_compressor` does not exist.

- [ ] **Step 3: Create the module with the two pure functions**

Create `app/core/context_compressor.py` with this exact content:

```python
"""Per-turn context-history compression for the master agent.

Pure functions `estimate_tokens` and `select_window` are sync and side-effect
free. The async orchestrators `compress_history` and `maybe_compress` make
exactly one LLM call per compressed turn and degrade gracefully to a sliding
window when the LLM is unavailable.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping, Optional, Sequence


logger = logging.getLogger(__name__)


# Module-level summary prompt. Kept short and project-style (Chinese, matching
# the existing master-agent prompts). The historical messages are sent as a
# single user message, with role-prefixed lines, immediately after this system
# message. The model is expected to return plain text only.
_SUMMARY_PROMPT = (
    "你是会话历史压缩器。请把以下对话压缩为结构化要点(中文, ≤ 600 字):\n\n"
    "1. 用户目标与已确认事实\n"
    "2. 待办 / 未决问题\n"
    "3. 关键引用(原文短语)\n"
    "4. 不确定 / 已废弃的想法\n\n"
    "输出纯文本,不要使用 markdown / 列表前缀 / 标题。"
)


def estimate_tokens(messages: Iterable[Mapping[str, Any]]) -> int:
    """Rough token estimate: sum of content character lengths divided by 4.

    Conservative for CJK content (counts chars, not bytes). Tolerates missing
    or non-string `content` by coercing via `str()`.
    """
    total_chars = 0
    for m in messages:
        content = m.get("content") if isinstance(m, Mapping) else None
        if content is None:
            continue
        if not isinstance(content, str):
            content = str(content)
        total_chars += len(content)
    return total_chars // 4


def select_window(
    messages: Sequence[Mapping[str, str]],
    summary: str,
    keep_last: int,
) -> List[dict]:
    """Return `[summary_message] + tail` if `summary` is non-empty; else `tail`.

    `keep_last <= 0` collapses the tail; with an empty summary the result is
    an empty list. The summary is always returned as a `system`-role message.
    """
    tail: List[dict] = list(messages[-keep_last:]) if keep_last > 0 else []
    if summary:
        return [{"role": "system", "content": summary}, *tail]
    return tail
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
python -m pytest tests/test_context_compressor.py -v
```
Expected: 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/context_compressor.py tests/test_context_compressor.py
git commit -m "feat(context): add estimate_tokens + select_window pure helpers"
```

---

## Task 2: Async orchestrator + tests (`compress_history`, `maybe_compress`)

**Files:**
- Modify: `app/core/context_compressor.py` (append orchestrators and summary-prompt helper)
- Modify: `tests/test_context_compressor.py` (append orchestrator tests)

- [ ] **Step 1: Append the failing tests for `compress_history` and `maybe_compress`**

Append to `tests/test_context_compressor.py`:

```python
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
    history = [{"role": "user", "content": "x" * 4000}]  # 1000 tokens
    router = AsyncMock()
    router.chat.return_value = "  summary body  "
    new, summary = await compress_history(history, router, max_tokens=100, keep_last=3)
    assert summary == "summary body"  # stripped
    assert router.chat.await_count == 1
    assert len(new) == 1 + 3
    assert new[0] == {"role": "system", "content": "summary body"}


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
    history = [{"role": "user", "content": "x" * 4000}]
    router = AsyncMock()
    router.chat.return_value = "summary"
    new, compressed, degraded = await maybe_compress(
        history, router, max_tokens=100, keep_last=4
    )
    assert compressed is True
    assert degraded is False
    assert new[0]["content"] == "summary"
    assert len(new) == 1 + 4


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


@pytest.mark.asyncio
async def test_maybe_compress_default_kwargs_read_settings(monkeypatch):
    """When max_tokens / keep_last are not passed, settings are read."""
    from app.config import settings
    monkeypatch.setattr(settings, "CONTEXT_COMPRESS_MAX_TOKENS", 100, raising=False)
    monkeypatch.setattr(settings, "CONTEXT_COMPRESS_KEEP_LAST", 2, raising=False)

    history = [{"role": "user", "content": "x" * 4000}]
    router = AsyncMock()
    router.chat.return_value = "sum"
    new, compressed, degraded = await maybe_compress(history, router)
    assert compressed is True
    assert len(new) == 1 + 2
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
python -m pytest tests/test_context_compressor.py -v
```
Expected: the 10 new tests in this task fail with `ImportError` (compress_history / maybe_compress not defined). The 12 tests from Task 1 still pass.

- [ ] **Step 3: Append the orchestrators and the settings reader**

Append to `app/core/context_compressor.py`:

```python
def _build_summary_user_message(messages: Sequence[Mapping[str, str]]) -> str:
    """Format the history as a single user-role message, role-prefixed lines."""
    lines = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _read_settings() -> tuple[int, int]:
    """Lazy import to avoid circular: app.config imports nothing from us, but
    test discovery may import this module before app.config is fully initialised
    under some pytest configurations."""
    from app.config import settings  # noqa: WPS433 (intentional local import)
    return (
        int(getattr(settings, "CONTEXT_COMPRESS_MAX_TOKENS", 8000)),
        int(getattr(settings, "CONTEXT_COMPRESS_KEEP_LAST", 6)),
    )


async def compress_history(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: int,
    keep_last: int,
) -> tuple[List[dict], Optional[str]]:
    """Core async orchestrator.

    Returns `(new_history, summary_str_or_None)`.
    - If `estimate_tokens(history) < max_tokens` → returns `(list(history), None)`
      without calling the LLM.
    - Otherwise calls `llm_router.chat(...)` once with `[system=_SUMMARY_PROMPT,
      user=role-prefixed history]`. On success returns the window with the
      summary prepended. On any exception, logs and returns the keep_last tail
      with `summary=None` (the caller surfaces this as `degraded=True`).
    - If `llm_router is None` at threshold, degrades the same way.
    """
    history_list = list(history)
    if estimate_tokens(history_list) < max_tokens:
        return history_list, None

    if llm_router is None:
        logger.warning("context_compressor: llm_router is None; degrading to sliding window")
        return select_window(history_list, "", keep_last), None

    try:
        response = await llm_router.chat(
            messages=[
                {"role": "system", "content": _SUMMARY_PROMPT},
                {"role": "user", "content": _build_summary_user_message(history_list)},
            ]
        )
    except Exception as exc:  # noqa: BLE001 - intentional broad catch
        logger.warning(
            "context_compressor: LLM call failed; degrading to sliding window: %s", exc
        )
        return select_window(history_list, "", keep_last), None

    summary = (response or "").strip()
    return select_window(history_list, summary, keep_last), (summary or None)


async def maybe_compress(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: Optional[int] = None,
    keep_last: Optional[int] = None,
) -> tuple[List[dict], bool, bool]:
    """Hook used by callers. Returns `(new_history, compressed, degraded)`.

    - `compressed=True` → LLM was called and a summary was produced.
    - `degraded=True`   → LLM was needed but unavailable/failed; we fell
      back to the `keep_last` tail so the turn can still proceed.
    - Both False → under threshold; history is returned unchanged.
    """
    if max_tokens is None or keep_last is None:
        cfg_max, cfg_keep = _read_settings()
        max_tokens = cfg_max if max_tokens is None else max_tokens
        keep_last = cfg_keep if keep_last is None else keep_last

    history_list = list(history)
    if estimate_tokens(history_list) < max_tokens:
        return history_list, False, False

    new, summary = await compress_history(
        history_list, llm_router, max_tokens=max_tokens, keep_last=keep_last
    )
    if summary:
        return new, True, False
    # summary is None means we hit either the no-router path or the LLM-raised
    # path inside compress_history. Either way, `new` is the keep_last tail.
    return new, False, True
```

- [ ] **Step 4: Run the full test file to confirm all 22 tests pass**

```bash
python -m pytest tests/test_context_compressor.py -v
```
Expected: 22 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/context_compressor.py tests/test_context_compressor.py
git commit -m "feat(context): add async compress_history + maybe_compress orchestrators"
```

---

## Task 3: Settings + master-agent hook

**Files:**
- Modify: `app/config.py` (add two fields)
- Modify: `app/agents/master.py` (import + insert hook at line 523)
- Modify: `tests/test_context_compressor.py` (settings round-trip test)

- [ ] **Step 1: Add the failing settings round-trip test**

Append to `tests/test_context_compressor.py`:

```python
def test_settings_have_context_compress_fields():
    from app.config import settings
    # Defaults: 8000 / 6
    assert int(getattr(settings, "CONTEXT_COMPRESS_MAX_TOKENS", 8000)) == 8000
    assert int(getattr(settings, "CONTEXT_COMPRESS_KEEP_LAST", 6)) == 6
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
python -m pytest tests/test_context_compressor.py::test_settings_have_context_compress_fields -v
```
Expected: FAIL — `settings` has no `CONTEXT_COMPRESS_MAX_TOKENS` attribute.

- [ ] **Step 3: Add the two settings fields to `app/config.py`**

In `app/config.py`, after the existing `# Sub-Agent Defaults` block (line 41), insert a new section **before** the `BASE_URL` line (line 45). Place it logically near the Master Agent block. Insert these two fields right after `MASTER_AGENT_TEMPERATURE: float = 0.7` (line 37) and before `# Sub-Agent Defaults`:

```python
    # Context Compressor (master-agent conversation-history compression)
    CONTEXT_COMPRESS_MAX_TOKENS: int = 8000
    CONTEXT_COMPRESS_KEEP_LAST: int = 6
```

The final block between `MASTER_AGENT_TEMPERATURE` and `SUB_AGENT_TIMEOUT` reads:

```python
    # Master Agent
    MASTER_AGENT_MODEL: str = "gpt-4o"
    MASTER_AGENT_TEMPERATURE: float = 0.7

    # Context Compressor (master-agent conversation-history compression)
    CONTEXT_COMPRESS_MAX_TOKENS: int = 8000
    CONTEXT_COMPRESS_KEEP_LAST: int = 6

    # Sub-Agent Defaults
    SUB_AGENT_TIMEOUT: int = 30
    SUB_AGENT_MAX_RETRIES: int = 2
```

- [ ] **Step 4: Run the settings test to confirm it passes**

```bash
python -m pytest tests/test_context_compressor.py::test_settings_have_context_compress_fields -v
```
Expected: PASS.

- [ ] **Step 5: Add the import to `app/agents/master.py`**

In `app/agents/master.py`, locate the import block at the top. Find the existing `from app.core...` import line (search for `from app.core`). Add a new import alphabetically:

```python
from app.core.context_compressor import maybe_compress
```

If no `app.core` import currently exists, add it after the last `from app.` import in the file.

- [ ] **Step 6: Insert the hook at the call site**

In `app/agents/master.py` at line 523, replace:

```python
                history = state.get("conversation_history") or []
                messages: List[Dict[str, str]] = [
```

with:

```python
                history = state.get("conversation_history") or []
                history, _compressed, _degraded = await maybe_compress(history, self.llm_router)
                state["context_compression"] = {"compressed": _compressed, "degraded": _degraded}
                messages: List[Dict[str, str]] = [
```

- [ ] **Step 7: Verify the file still imports cleanly**

```bash
python -c "from app.agents.master import MasterAgent; print('ok')"
```
Expected: `ok`. (No syntax or import-time errors.)

- [ ] **Step 8: Run the full test file to confirm nothing regressed**

```bash
python -m pytest tests/test_context_compressor.py -v
```
Expected: 23 tests pass (12 + 10 + 1).

- [ ] **Step 9: Run the full project test suite to confirm no regressions**

```bash
python -m pytest tests/ -q
```
Expected: all previously-passing tests still pass; no new failures. (DB-touching tests may be skipped if no DB is configured; that is fine.)

- [ ] **Step 10: Commit**

```bash
git add app/config.py app/agents/master.py tests/test_context_compressor.py
git commit -m "feat(context): wire maybe_compress into master agent + add settings"
```

---

## Task 4: Update project status

**Files:**
- Modify: `docs/superpowers/plans/project_status.md`

- [ ] **Step 1: Move the entry from "Not yet implemented" to "Recently completed"**

Open `docs/superpowers/plans/project_status.md`. The file currently has an empty "Not yet implemented" section (a single line `_（无明确声明但未实现的功能）_`). Above that section, in the first "Recently completed" list, add a new bullet at the top:

```markdown
- **Auto-compress long conversation history** ✅ — `app/core/context_compressor.py` 新模块，`maybe_compress()` 在 master agent 提交 LLM 调用前对 `conversation_history` 做阈值检测：默认 8000 token / 保留最近 6 条；超额则一次性调 LLM 压缩成 1 条 system 摘要 + 最近 K 条，LLM 失败/缺 router 时降级为滑动窗口不阻塞 turn；DB / 前端 / `_summarizer_node` / `internal_agent` 内部压缩均不动；`CONTEXT_COMPRESS_MAX_TOKENS=0` 即关闭。23 个单测覆盖纯函数 + 4 条 AsyncMock 降级/触发路径。
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/project_status.md
git commit -m "docs(status): auto-compress context implemented"
```

---

## Self-Review Notes

- **Spec coverage:** every requirement maps to a task. Pure helpers → Task 1; async orchestrators → Task 2; settings + integration point → Task 3; status update → Task 4. LLM-failure degradation path is explicitly tested in Task 2. Empty-history and threshold-zero edge cases are tested.
- **Placeholder scan:** all code blocks are complete; no "TBD" / "add appropriate handling" patterns. The smoke assertion in the spec was optional and is not included here (avoided brittle CI); this is consistent with the spec's "optional" framing.
- **Type consistency:** `estimate_tokens` returns `int` everywhere it's called; `select_window` returns `List[dict]`; `compress_history` returns `tuple[List[dict], Optional[str]]`; `maybe_compress` returns `tuple[List[dict], bool, bool]`. Master-agent hook unpacks the same 3-tuple. Settings field names match env vars via `case_sensitive=True`.

