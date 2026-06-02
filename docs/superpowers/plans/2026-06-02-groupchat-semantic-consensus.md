# Group-Chat Semantic Consensus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace group-chat consensus detection's crude Jaccard word-overlap with a hybrid: embedding cosine similarity, an LLM judge for the ambiguous band, and the existing Jaccard heuristic as a last-resort fallback — with configurable thresholds.

**Architecture:** `GroupChatService._check_consensus` becomes a thin orchestrator over small helpers in `app/services/group_chat.py`. It embeds the agents' last responses via `router.embed`, compares each to the first ("anchor") by cosine, and uses the weakest pair (`min_cos`): `>= HIGH` → consensus, `< LOW` → no consensus, gray band (or embedding failure) → LLM judge, judge `None` → Jaccard. The check never raises (it runs inside the discussion loop).

**Tech Stack:** Python, pytest (`asyncio_mode = "auto"`; tests keep the `@pytest.mark.asyncio` convention). Reuses `get_llm_router().embed/.chat`. Pure-Python cosine (no numpy dependency).

**Spec:** `docs/superpowers/specs/2026-06-02-groupchat-semantic-consensus-design.md`
**Issue:** [#14](https://github.com/pz1130/CyberGuard-AI/issues/14)

**Run tests with the project venv:** `.venv/bin/python -m pytest ...`

---

## File Structure

- **Modify** `app/config.py` — add 3 settings (`GROUPCHAT_CONSENSUS_HIGH`, `GROUPCHAT_CONSENSUS_LOW`, `GROUPCHAT_JACCARD_THRESHOLD`).
- **Modify** `app/services/group_chat.py`:
  - add module-level `_cosine(a, b)` pure helper;
  - add methods `_first_agent_provider_id`, `_jaccard_consensus`, `_llm_judge_consensus`;
  - rewrite `_check_consensus`;
  - refactor `_generate_summary` to reuse `_first_agent_provider_id` (DRY);
  - keep `_text_similarity` unchanged.
- **Create** `tests/test_group_chat_consensus.py` — all tests for the new behavior.

**Branch:** create `feat/groupchat-semantic-consensus` off `main` before Task 1 (do NOT commit to `main`).

---

### Task 0: Create feature branch

- [ ] **Step 1: Branch off main**

```bash
git checkout main && git pull --ff-only origin main
git checkout -b feat/groupchat-semantic-consensus
```

---

### Task 1: Config thresholds + test scaffold

**Files:**
- Modify: `app/config.py` (after `MOCK_MODE: bool = False`, near the attachment-cap settings)
- Create: `tests/test_group_chat_consensus.py`

- [ ] **Step 1: Create the test file with shared helpers + the failing config test**

Create `tests/test_group_chat_consensus.py`:

```python
"""Tests for group-chat hybrid semantic consensus (issue #14)."""
import pytest

from app.services.group_chat import (
    GroupChatService,
    GroupChatSession,
    GroupChatMessage,
)


class FakeRouter:
    """Stand-in for the LLM router. Configure embed/chat results or errors."""

    def __init__(self, *, embed_result=None, embed_error=None,
                 chat_result=None, chat_error=None):
        self.embed_result = embed_result
        self.embed_error = embed_error
        self.chat_result = chat_result
        self.chat_error = chat_error
        self.embed_calls = []
        self.chat_calls = []

    async def embed(self, texts, model=None, provider_id=None):
        self.embed_calls.append({"texts": texts, "provider_id": provider_id})
        if self.embed_error is not None:
            raise self.embed_error
        return self.embed_result

    async def chat(self, messages=None, provider_id=None, **kwargs):
        self.chat_calls.append({"messages": messages, "provider_id": provider_id})
        if self.chat_error is not None:
            raise self.chat_error
        return self.chat_result


def _make_consensus_session(responses):
    """A session with one user msg + one agent msg per response."""
    s = GroupChatSession(
        session_id="consensus-test",
        user_id=1,
        agent_ids=list(range(1, len(responses) + 1)),
    )
    s.messages.append(GroupChatMessage(role="user", content="question"))
    for i, r in enumerate(responses):
        s.messages.append(GroupChatMessage(role="agent", content=r, agent_id=i + 1))
    return s


def test_groupchat_consensus_settings_defaults():
    from app.config import settings
    assert settings.GROUPCHAT_CONSENSUS_HIGH == 0.85
    assert settings.GROUPCHAT_CONSENSUS_LOW == 0.65
    assert settings.GROUPCHAT_JACCARD_THRESHOLD == 0.7
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'GROUPCHAT_CONSENSUS_HIGH'`

- [ ] **Step 3: Add the settings**

In `app/config.py`, immediately after the line `ATTACHMENT_TOTAL_MAX_CHARS: int = 24000` (the attachment caps added in the previous feature), add:

```python
    # Group-chat consensus detection (issue #14)
    GROUPCHAT_CONSENSUS_HIGH: float = 0.85      # min cosine >= HIGH => consensus
    GROUPCHAT_CONSENSUS_LOW: float = 0.65       # min cosine < LOW  => no consensus
    GROUPCHAT_JACCARD_THRESHOLD: float = 0.7    # lexical fallback threshold
```

If those attachment lines are not present for some reason, add the block immediately after `MOCK_MODE: bool = False` instead. Match the surrounding pydantic field style.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_group_chat_consensus.py
git commit -m "feat(config): add group-chat consensus thresholds + test scaffold (#14)"
```

---

### Task 2: `_cosine` pure helper

**Files:**
- Modify: `app/services/group_chat.py` (add module-level function after `_cancel_key`, ~line 20)
- Test: `tests/test_group_chat_consensus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_group_chat_consensus.py` (and add `_cosine` to the import from `app.services.group_chat` at the top of the file — add a separate line `from app.services.group_chat import _cosine`):

```python
def test_cosine_identical_is_one():
    assert _cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_zero_vector_is_zero():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_length_mismatch_is_zero():
    assert _cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_known_value():
    # angle between (1,0) and (1,1) is 45deg -> cos = 1/sqrt(2)
    assert _cosine([1.0, 0.0], [1.0, 1.0]) == pytest.approx(0.7071, abs=1e-4)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k cosine -v`
Expected: FAIL — `ImportError: cannot import name '_cosine'`

- [ ] **Step 3: Implement `_cosine`**

In `app/services/group_chat.py`, add this module-level function right after the `_cancel_key` function (around line 20, before the `@dataclass` declarations):

```python
def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity of two equal-length vectors.

    Returns 0.0 when the vectors differ in length or either has zero norm.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
```

(`List` is already imported at the top of the file via `from typing import Dict, List, Optional, Any`.)

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k cosine -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_consensus.py
git commit -m "feat(groupchat): add pure-python cosine similarity helper (#14)"
```

---

### Task 3: Extract `_first_agent_provider_id` (DRY) and reuse in `_generate_summary`

**Files:**
- Modify: `app/services/group_chat.py` (add `_first_agent_provider_id` method; refactor `_generate_summary`)
- Test: `tests/test_group_chat_consensus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_group_chat_consensus.py`:

```python
@pytest.mark.asyncio
async def test_first_agent_provider_id_none_when_no_agents():
    service = GroupChatService()
    session = GroupChatSession(session_id="x", user_id=1, agent_ids=[])
    assert await service._first_agent_provider_id(session) is None


@pytest.mark.asyncio
async def test_generate_summary_uses_first_agent_provider_id(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["agent says hello"])

    async def _pid(s):
        return 42
    monkeypatch.setattr(service, "_first_agent_provider_id", _pid)

    fake = FakeRouter(chat_result="summary text")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)

    await service._generate_summary(session)
    assert fake.chat_calls and fake.chat_calls[0]["provider_id"] == 42
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k "first_agent or generate_summary" -v`
Expected: FAIL — `AttributeError: 'GroupChatService' object has no attribute '_first_agent_provider_id'`

- [ ] **Step 3: Add `_first_agent_provider_id` and refactor `_generate_summary`**

In `app/services/group_chat.py`, add this method to `GroupChatService` (place it just before `_generate_summary`, after `_text_similarity`):

```python
    async def _first_agent_provider_id(self, session: GroupChatSession) -> Optional[int]:
        """Return the llm_provider_id of the first participating agent, or None."""
        if not session.agent_ids:
            return None
        from app.core.database import AsyncSessionLocal
        from app.models.agent import AgentConfig
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AgentConfig).where(AgentConfig.id == session.agent_ids[0])
            )
            agent_obj = result.scalar_one_or_none()
            return agent_obj.llm_provider_id if agent_obj else None
```

Then in `_generate_summary`, replace the inline provider lookup block. The current code reads:

```python
            from app.services.llm_router import get_llm_router
            from app.core.database import AsyncSessionLocal
            from app.models.agent import AgentConfig
            from sqlalchemy import select

            # Build a transcript of all agent responses
            transcript_lines: List[str] = []
            for m in session.messages:
                if m.role == "agent" and m.content:
                    name = m.agent_name or f"Agent-{m.agent_id}"
                    transcript_lines.append(f"[{name}]: {m.content}")

            if not transcript_lines:
                return

            # Get provider_id from the first participating agent
            provider_id = None
            if session.agent_ids:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(AgentConfig).where(AgentConfig.id == session.agent_ids[0])
                    )
                    agent_obj = result.scalar_one_or_none()
                    if agent_obj:
                        provider_id = agent_obj.llm_provider_id
```

Replace it with (drop the now-unused `AsyncSessionLocal`/`AgentConfig`/`select` imports; keep `get_llm_router`):

```python
            from app.services.llm_router import get_llm_router

            # Build a transcript of all agent responses
            transcript_lines: List[str] = []
            for m in session.messages:
                if m.role == "agent" and m.content:
                    name = m.agent_name or f"Agent-{m.agent_id}"
                    transcript_lines.append(f"[{name}]: {m.content}")

            if not transcript_lines:
                return

            provider_id = await self._first_agent_provider_id(session)
```

Leave the rest of `_generate_summary` (prompt construction, `router.chat`, summary append, `except`) unchanged.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k "first_agent or generate_summary" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_consensus.py
git commit -m "refactor(groupchat): extract _first_agent_provider_id, reuse in summary (#14)"
```

---

### Task 4: `_jaccard_consensus` fallback (extracted, configurable threshold)

**Files:**
- Modify: `app/services/group_chat.py` (add `_jaccard_consensus`; add `from app.config import settings` to top imports)
- Test: `tests/test_group_chat_consensus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_group_chat_consensus.py`:

```python
def test_jaccard_consensus_identical_true():
    service = GroupChatService()
    assert service._jaccard_consensus(["block the ip", "block the ip"]) is True


def test_jaccard_consensus_dissimilar_false():
    service = GroupChatService()
    assert service._jaccard_consensus(["block the ip now", "let us order pizza"]) is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k jaccard -v`
Expected: FAIL — `AttributeError: 'GroupChatService' object has no attribute '_jaccard_consensus'`

- [ ] **Step 3: Add the settings import and `_jaccard_consensus`**

In `app/services/group_chat.py`, add to the top-level imports (after `from app.services.agent_executor import AgentExecutor`):

```python
from app.config import settings
```

Then add this method to `GroupChatService` (place it just after `_text_similarity`):

```python
    def _jaccard_consensus(self, responses: List[str]) -> bool:
        """Lexical fallback: anchor-vs-others Jaccard word overlap."""
        anchor = (responses[0] or "").lower()
        threshold = settings.GROUPCHAT_JACCARD_THRESHOLD
        similar_count = sum(
            1 for r in responses[1:]
            if self._text_similarity(anchor, (r or "").lower()) > threshold
        )
        return similar_count >= len(responses) - 1
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k jaccard -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_consensus.py
git commit -m "feat(groupchat): extract jaccard fallback with configurable threshold (#14)"
```

---

### Task 5: `_llm_judge_consensus`

**Files:**
- Modify: `app/services/group_chat.py` (add `_llm_judge_consensus` method)
- Test: `tests/test_group_chat_consensus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_group_chat_consensus.py`:

```python
@pytest.mark.asyncio
async def test_judge_yes_true(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="YES")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is True
    assert fake.chat_calls and fake.chat_calls[0]["provider_id"] is None


@pytest.mark.asyncio
async def test_judge_no_false(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="No, they differ.")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is False


@pytest.mark.asyncio
async def test_judge_unparseable_none(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="maybe, unclear")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is None


@pytest.mark.asyncio
async def test_judge_empty_none(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is None


@pytest.mark.asyncio
async def test_judge_error_none(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_error=RuntimeError("llm down"))
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k judge -v`
Expected: FAIL — `AttributeError: 'GroupChatService' object has no attribute '_llm_judge_consensus'`

- [ ] **Step 3: Implement `_llm_judge_consensus`**

In `app/services/group_chat.py`, add this method to `GroupChatService` (place it just after `_jaccard_consensus`):

```python
    async def _llm_judge_consensus(
        self, responses: List[str], provider_id: Optional[int]
    ) -> Optional[bool]:
        """Ask an LLM whether the responses substantively agree.

        Returns True/False, or None when the call fails or the answer is
        unparseable (so the caller can fall back to the lexical heuristic).
        """
        try:
            from app.services.llm_router import get_llm_router
            numbered = "\n\n".join(
                f"[Response {i + 1}]: {r}" for i, r in enumerate(responses)
            )
            prompt = (
                "You are judging whether multiple agents have reached consensus.\n\n"
                f"{numbered}\n\n"
                "Do these responses substantively agree on the same conclusion? "
                "Answer with exactly YES or NO."
            )
            router = get_llm_router()
            answer = await router.chat(
                messages=[{"role": "user", "content": prompt}],
                provider_id=provider_id,
            )
            text = (answer or "").strip().lower()
            if text.startswith("yes"):
                return True
            if text.startswith("no"):
                return False
            return None
        except Exception as e:  # noqa: BLE001 - consensus check must not raise
            import logging
            logging.getLogger(__name__).warning(f"[consensus] LLM judge failed: {e}")
            return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k judge -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_consensus.py
git commit -m "feat(groupchat): add LLM judge for consensus gray band (#14)"
```

---

### Task 6: Rewrite `_check_consensus` as hybrid orchestrator

**Files:**
- Modify: `app/services/group_chat.py` (replace the body of `_check_consensus`)
- Test: `tests/test_group_chat_consensus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_group_chat_consensus.py`:

```python
def _patch_no_provider(monkeypatch, service):
    async def _no_provider(s):
        return None
    monkeypatch.setattr(service, "_first_agent_provider_id", _no_provider)


@pytest.mark.asyncio
async def test_consensus_all_high_cosine_true_no_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["block the IP", "block the IP now"])
    fake = FakeRouter(embed_result=[[1.0, 0.0], [1.0, 0.0]])  # cos 1.0
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)
    judge_calls = {"n": 0}

    async def _judge(responses, provider_id):
        judge_calls["n"] += 1
        return True
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is True
    assert judge_calls["n"] == 0


@pytest.mark.asyncio
async def test_consensus_below_low_false_no_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["block the IP", "open all ports"])
    fake = FakeRouter(embed_result=[[1.0, 0.0], [0.0, 1.0]])  # cos 0.0
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)
    judge_calls = {"n": 0}

    async def _judge(responses, provider_id):
        judge_calls["n"] += 1
        return True
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is False
    assert judge_calls["n"] == 0


@pytest.mark.asyncio
async def test_consensus_gray_band_invokes_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["resp a", "resp b"])
    fake = FakeRouter(embed_result=[[1.0, 0.0], [1.0, 1.0]])  # cos ~0.707 (gray)
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)
    judge_calls = {"n": 0}

    async def _judge(responses, provider_id):
        judge_calls["n"] += 1
        return True
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is True
    assert judge_calls["n"] == 1


@pytest.mark.asyncio
async def test_consensus_embed_error_routes_to_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["resp a", "resp b"])
    fake = FakeRouter(embed_error=RuntimeError("no embed provider"))
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)

    async def _judge(responses, provider_id):
        return False
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is False


@pytest.mark.asyncio
async def test_consensus_judge_none_falls_back_to_jaccard(monkeypatch):
    service = GroupChatService()
    # identical responses -> Jaccard returns True
    session = _make_consensus_session(["block the ip now", "block the ip now"])
    fake = FakeRouter(embed_error=RuntimeError("no embed"))
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)

    async def _judge(responses, provider_id):
        return None
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is True


@pytest.mark.asyncio
async def test_consensus_too_few_messages_false():
    service = GroupChatService()
    session = GroupChatSession(session_id="x", user_id=1, agent_ids=[1, 2])
    session.messages.append(GroupChatMessage(role="user", content="q"))
    assert await service._check_consensus(session) is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -k consensus -v`
Expected: FAIL — the old `_check_consensus` ignores the mocked router/judge, so the cosine-path assertions (e.g. `judge_calls["n"] == 1`, embed-error routing) fail.

- [ ] **Step 3: Rewrite `_check_consensus`**

In `app/services/group_chat.py`, replace the entire current `_check_consensus` method body with:

```python
    async def _check_consensus(self, session: GroupChatSession) -> bool:
        """Check whether agents have reached consensus.

        Hybrid: embedding cosine similarity (weakest anchor-vs-other pair), an
        LLM judge for the ambiguous band or on embedding failure, and the
        Jaccard heuristic as a final fallback. Never raises — it runs inside
        the discussion loop.
        """
        if len(session.messages) < len(session.agent_ids) + 1:
            return False

        agent_responses = [
            m.content for m in session.messages[-len(session.agent_ids):]
            if m.role == "agent"
        ]
        if len(agent_responses) < len(session.agent_ids):
            return False
        if len(agent_responses) < 2:
            return False

        provider_id = await self._first_agent_provider_id(session)

        # 1. Embedding cosine path.
        try:
            from app.services.llm_router import get_llm_router
            router = get_llm_router()
            vectors = await router.embed(agent_responses, provider_id=provider_id)
            min_cos = min(_cosine(vectors[0], v) for v in vectors[1:])
            if min_cos >= settings.GROUPCHAT_CONSENSUS_HIGH:
                return True
            if min_cos < settings.GROUPCHAT_CONSENSUS_LOW:
                return False
            # gray band -> fall through to the LLM judge
        except Exception as e:  # noqa: BLE001 - degrade to judge/Jaccard, never raise
            import logging
            logging.getLogger(__name__).warning(
                f"[consensus] embedding similarity failed, using LLM judge: {e}"
            )

        # 2. LLM judge (gray band or embedding failure).
        verdict = await self._llm_judge_consensus(agent_responses, provider_id)
        if verdict is not None:
            return verdict

        # 3. Lexical fallback.
        return self._jaccard_consensus(agent_responses)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add app/services/group_chat.py tests/test_group_chat_consensus.py
git commit -m "feat(groupchat): hybrid semantic consensus (cosine + LLM judge + jaccard) (#14)

Resolves #14."
```

---

### Task 7: Final verification + PR

- [ ] **Step 1: Run the new suite plus existing group-chat tests (no regressions)**

Run: `.venv/bin/python -m pytest tests/test_group_chat_consensus.py tests/test_group_chat_completion.py tests/test_group_chat_multiworker.py -v`
Expected: all pass.

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin feat/groupchat-semantic-consensus
gh pr create --title "feat: hybrid semantic group-chat consensus (#14)" \
  --body "Implements docs/superpowers/specs/2026-06-02-groupchat-semantic-consensus-design.md. Closes #14."
```

---

## Self-Review

**Spec coverage:**
- Embedding cosine path with `min_cos` HIGH/LOW bands → Task 6. ✓
- `_cosine` pure helper (no numpy) → Task 2. ✓
- LLM judge for gray band + embedding failure → Tasks 5, 6. ✓
- Jaccard retained as final fallback, configurable threshold → Tasks 4, 6. ✓
- `_first_agent_provider_id` extraction + reuse in `_generate_summary` (DRY) → Task 3. ✓
- Three config thresholds → Task 1. ✓
- Never raises; guards incl. `< 2 responses` (prevents `min()` on empty) → Task 6. ✓
- Testing: `_cosine`, hybrid branches (all-high/below-low/gray/embed-error/judge-none/guards), judge YES/NO/garbage/empty/error, config defaults → Tasks 1-6. ✓
- Out-of-scope items (caching, all-pairs, model tuning, persistence) → not implemented. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✓

**Type consistency:** `_cosine(a, b) -> float`; `_first_agent_provider_id(session) -> Optional[int]` (async); `_jaccard_consensus(responses) -> bool`; `_llm_judge_consensus(responses, provider_id) -> Optional[bool]` (async); `_check_consensus(session) -> bool` (async). `settings.GROUPCHAT_CONSENSUS_HIGH/LOW`, `settings.GROUPCHAT_JACCARD_THRESHOLD`. `router.embed(texts, provider_id=...)`, `router.chat(messages=..., provider_id=...)`. Names/signatures consistent across tasks and tests. ✓
