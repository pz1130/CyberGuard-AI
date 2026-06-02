# Group-Chat Semantic Consensus — Design

**Issue:** [#14](https://github.com/pz1130/CyberGuard-AI/issues/14) — Group-chat consensus uses crude word-overlap, not semantic similarity
**Date:** 2026-06-02
**Status:** Approved (brainstorming)

## Problem

`GroupChatSession._check_consensus` (`app/services/group_chat.py:327-368`) decides whether
agents agree using **Jaccard word-overlap** (`_text_similarity`, threshold `0.7`),
comparing each agent's last response to the first agent's (an "anchor"). This detects
literal word reuse, not semantic agreement:

- **Paraphrases / synonyms fail** — agents that agree in meaning but differ in wording
  score as non-consensus.
- **Boilerplate inflates agreement** — shared greetings/formatting/role preambles can
  push unrelated responses over threshold.
- Word-set Jaccard ignores ordering and emphasis.

The code already carries the note `# In production, use embedding similarity`.

## Approach

**Hybrid: embedding cosine similarity with an LLM judge for the ambiguous band, and the
existing Jaccard heuristic retained as a last-resort fallback.** `_check_consensus`
becomes a thin orchestrator over small, independently testable helpers. It must never
raise — it runs inside the discussion loop — so every external call degrades down a
chain whose worst case is today's Jaccard behavior.

### Available infrastructure

- `get_llm_router().embed(texts, model=None, provider_id=None) -> List[List[float]]`
  (OpenAI-compatible `/embeddings`). Requires a configured embedding provider; raises
  when unavailable.
- `get_llm_router().chat(messages, provider_id=None) -> str` — used already by
  `_generate_summary`.
- `provider_id` is resolved from the first participating agent's `llm_provider_id`
  (the pattern `_generate_summary` uses today).
- numpy is installed transitively, but cosine is trivial in pure Python — **no new
  dependency**.

### Decision flow

Uses the **weakest** anchor-vs-other cosine (`min_cos`), so consensus requires *all*
agents to agree with the anchor:

```
collect last response per agent      (existing guards unchanged)
        │
  router.embed(responses) ──error──────────────┐
        │                                       │
   min_cos = min(cosine(r0, ri) for i>0)        │
        │                                       │
   min_cos >= HIGH  -> True                      │
   min_cos <  LOW   -> False                      │
   LOW <= min_cos < HIGH (gray) -> LLM judge ◄───┘   (embed failure also routes here)
                         │
            "YES" -> True / "NO" -> False / unparseable|error -> None
                         │
                       None -> Jaccard consensus (kept)
```

## Components

All in `app/services/group_chat.py` unless noted.

### `_cosine(a: List[float], b: List[float]) -> float`
Pure function. Standard cosine similarity. Returns `0.0` when either vector has zero
norm or lengths differ. No numpy.

### `_check_consensus(self, session) -> bool` (rewritten orchestrator)
1. Keep the existing guards: `len(session.messages) < len(session.agent_ids) + 1` →
   `False`; collect `agent_responses` = last response per agent; if fewer than
   `len(session.agent_ids)` → `False`. With `< 2` responses → `False` (nothing to
   compare).
2. Resolve `provider_id` via `_first_agent_provider_id(session)`.
3. Embedding path (wrapped in try/except):
   - `vectors = await router.embed(agent_responses, provider_id=provider_id)`
   - `min_cos = min(_cosine(vectors[0], v) for v in vectors[1:])`
   - `>= GROUPCHAT_CONSENSUS_HIGH` → return `True`
   - `< GROUPCHAT_CONSENSUS_LOW` → return `False`
   - otherwise → go to LLM judge
   - on any exception → go to LLM judge
4. LLM judge: `verdict = await _llm_judge_consensus(agent_responses, provider_id)`
   - `True`/`False` → return it
   - `None` → fall through to Jaccard
5. Jaccard fallback: return `_jaccard_consensus(agent_responses)`.

### `_llm_judge_consensus(self, responses, provider_id) -> Optional[bool]`
Builds a prompt listing the numbered responses and asking: *"Do these responses
substantively agree on the same conclusion? Answer with exactly YES or NO."* Calls
`router.chat(messages=[{"role":"user","content":prompt}], provider_id=provider_id)`.
Parses case-insensitively: leading/standalone `yes` → `True`, `no` → `False`. Returns
`None` on empty/unparseable output or any exception (logged at warning).

### `_jaccard_consensus(self, responses) -> bool`
The current lexical logic extracted verbatim: anchor = `responses[0].lower()`; count
others whose `_text_similarity(anchor, r.lower()) > GROUPCHAT_JACCARD_THRESHOLD`;
return `count >= len(responses) - 1`.

### `_first_agent_provider_id(self, session) -> Optional[int]`
Extracts the inline DB lookup currently in `_generate_summary` (select `AgentConfig`
by `session.agent_ids[0]`, return `llm_provider_id`). **Reused** by both
`_check_consensus` and `_generate_summary` (DRY cleanup). Returns `None` when there are
no agents or no row.

### `_text_similarity` — unchanged
Kept as-is; used by `_jaccard_consensus`.

## Configuration — `app/config.py`

Added to the `Settings` class (same style as existing fields):

- `GROUPCHAT_CONSENSUS_HIGH: float = 0.85` — `min_cos >=` ⇒ consensus
- `GROUPCHAT_CONSENSUS_LOW: float = 0.65` — `min_cos <` ⇒ no consensus
- `GROUPCHAT_JACCARD_THRESHOLD: float = 0.7` — fallback lexical threshold (was hardcoded)

## Error handling

`_check_consensus` never raises. Embedding errors route to the LLM judge; judge errors
or unparseable output route to Jaccard; Jaccard is pure and total. The discussion loop
always gets a clean `bool`.

## Acceptance mapping

- *Semantically-equivalent-but-differently-worded responses recognized as consensus* —
  embedding cosine; paraphrases score high.
- *Shared boilerplate alone does not trigger false consensus* — strict `HIGH=0.85`
  plus the gray-band LLM judge guard against boilerplate-inflated scores.
- *Threshold configurable* — three settings above.

## Testing

- `_cosine`: identical → `1.0`; orthogonal → `0.0`; zero vector → `0.0`; mismatched
  length → `0.0`; a known hand-computed value.
- `_check_consensus` (mock `router.embed`):
  - all pairs `>= HIGH` → `True`, and the LLM judge is **not** called.
  - some pair `< LOW` → `False`, judge **not** called.
  - all in gray band → judge **is** called (mock returns `True`/`False`, asserted).
  - `embed` raises → judge invoked.
  - judge returns `None` (mocked) → Jaccard fallback used (assert via crafted inputs).
- `_llm_judge_consensus`: mock `router.chat` → `"YES"` → `True`, `"NO"` → `False`,
  `"maybe..."`/`""` → `None`; chat raises → `None`.
- Guards: too few messages / too few responses → `False`.
- Config: defaults present and correct types.

## Out of scope (YAGNI)

- Caching embeddings across rounds.
- Pairwise all-vs-all comparison (anchor comparison retained).
- Embedding-model selection/tuning for consensus.
- Persisting consensus scores or judge rationales.
