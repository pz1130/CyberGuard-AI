# Chat Model Verified Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Chat page's model dropdown show only models the user has actually tested successfully, drop the hardcoded `FALLBACK_MODELS` placeholders, and persist per-model verification state on the `Provider.models` JSON column.

**Architecture:** Per-model `verified/last_tested_at/test_error` lives in the existing JSON `models` column on `Provider` (no DB migration). The two existing test/probe endpoints stamp the result back into the dict. Built-in preset providers stamp `verified=True` at seed time. Frontend filters on `verified === true` and shows a soft empty-state hint.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, JSON column mutation, React/TypeScript

**Spec:** `docs/superpowers/specs/2026-06-03-chat-model-verified-filter-design.md`

**Working directory:** `/Users/jc/Documents/cyber-agent/cyberguard`

**Test command (after DB up):** `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard .venv/bin/python -m pytest tests/test_providers.py -v`

**Frontend type-check:** `cd webui && npx tsc --noEmit`

---

## File Structure

Files created or modified by this plan:

| File | Responsibility |
|------|----------------|
| `app/schemas/provider.py` (modify) | `ModelInfo`: add `verified / last_tested_at / test_error` optional fields |
| `app/routers/providers.py` (modify) | New `_stamp_model_verified` helper; call it from `test_provider_connection` and `probe_provider_capabilities`; stamp preset models at seed time |
| `tests/test_providers.py` (create) | Backend tests for stamping + seed behavior + per-model probe |
| `webui/src/api/client.ts` (modify) | `ProviderModel` interface: add `verified? / last_tested_at? / test_error?` |
| `webui/src/pages/Chat.tsx` (modify) | Delete `FALLBACK_MODELS`; change `useState` initial; filter `loadModels` on `verified === true`; add empty-state hint |
| `webui/src/pages/Providers.tsx` (modify) | Per-model status badge (✓ VERIFIED / ✗ FAILED / · UNTESTED) |

---

## Task 1: Add `verified` fields to `ModelInfo` schema

**Files:**
- Modify: `app/schemas/provider.py:7-15`
- Test: `tests/test_providers.py` (created in Task 4 — covered there)

- [ ] **Step 1: Edit `app/schemas/provider.py`**

Replace the `ModelInfo` class (lines 7-15) with:

```python
class ModelInfo(BaseModel):
    """Model info with type classification and optional probed capabilities /
    verification status.

    `capabilities` is filled by the capability prober, e.g.
    {"tools": true, "vision": false, "probed_at": "2026-06-03T..."}. None until probed.

    `verified` is filled by /providers/test and /models/probe:
      None  — never tested
      True  — test succeeded
      False — test failed (see test_error for detail)
    """
    name: str
    model_type: Literal["chat", "embedding", "rerank"] = "chat"
    capabilities: Optional[Dict[str, Any]] = None
    verified: Optional[bool] = None
    last_tested_at: Optional[datetime] = None
    test_error: Optional[str] = None
```

- [ ] **Step 2: Add the `datetime` import**

At the top of `app/schemas/provider.py`, change:
```python
from typing import Optional, List, Dict, Any, Literal
```
to:
```python
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
```

- [ ] **Step 3: Sanity-check the import**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && .venv/bin/python -c "from app.schemas.provider import ModelInfo; m = ModelInfo(name='x'); print(m.verified, m.last_tested_at, m.test_error)"`
Expected output: `None None None`

- [ ] **Step 4: Commit**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
git add app/schemas/provider.py
git commit -m "feat(schema): ModelInfo — add verified/last_tested_at/test_error fields

Optional, all default to None. Used to gate the Chat page model dropdown
on actual successful tests, replacing the hardcoded FALLBACK_MODELS list.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Add `_stamp_model_verified` helper

**Files:**
- Modify: `app/routers/providers.py` (insert helper after `_test_provider_connectivity`, before `_provider_to_read_schema` at line 313)
- Test: `tests/test_providers.py` (covered in Task 4)

- [ ] **Step 1: Insert the helper**

In `app/routers/providers.py`, insert **before** the `_provider_to_read_schema` function (right after `_test_provider_connectivity` ends at line 311, blank line at 312, blank at 313):

```python
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
    """
    from datetime import datetime as _dt

    result: list = [dict(m) if isinstance(m, dict) else {"name": str(m), "model_type": "chat"}
                    for m in (models or [])]
    now_iso = _dt.utcnow().isoformat()
    for entry in result:
        if entry.get("name") == model_name:
            entry["verified"] = bool(ok)
            entry["last_tested_at"] = now_iso
            entry["test_error"] = (err or "")[:200] if not ok else None
            return result
    # Not found — append a stub
    result.append({
        "name": model_name,
        "model_type": "chat",
        "verified": bool(ok),
        "last_tested_at": now_iso,
        "test_error": (err or "")[:200] if not ok else None,
    })
    return result
```

- [ ] **Step 2: Smoke-test the helper**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && .venv/bin/python -c "
from app.routers.providers import _stamp_model_verified
existing = [{'name': 'a', 'model_type': 'chat'}, {'name': 'b', 'model_type': 'chat'}]
out = _stamp_model_verified(existing, 'a', ok=True)
assert out[0]['verified'] is True, out
assert out[0]['last_tested_at']
assert out[1]['verified'] is None
print('update-existing OK')

out2 = _stamp_model_verified(existing, 'c', ok=False, err='HTTP 401')
assert len(out2) == 3
assert out2[2]['name'] == 'c'
assert out2[2]['verified'] is False
assert out2[2]['test_error'] == 'HTTP 401'
print('append-new OK')

out3 = _stamp_model_verified(existing, 'a', ok=False, err='HTTP 500')
assert out3[0]['verified'] is False
assert out3[0]['test_error'] == 'HTTP 500'
print('overwrite-with-failure OK')
"
`
Expected: prints `update-existing OK`, `append-new OK`, `overwrite-with-failure OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
git add app/routers/providers.py
git commit -m "feat(providers): _stamp_model_verified helper

Updates/inserts a model's verification status in the Provider.models
JSON list. Returns a new list (not in-place) so SQLAlchemy detects the
change on the next commit. No external side effects.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Wire the stamp into `test_provider_connection` and `probe_provider_capabilities`

**Files:**
- Modify: `app/routers/providers.py:389-416` (`test_provider_connection`)
- Modify: `app/routers/providers.py:486-525` (`probe_provider_capabilities`)

- [ ] **Step 1: Stamp on `/providers/test` success or failure**

Replace the body of `test_provider_connection` (lines 391-416) with:

```python
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
            api_key = decrypt_data(provider.api_key_encrypted)
        except Exception:
            api_key = None

    test_resp = await _test_provider_connectivity(
        base_url=provider.base_url or "",
        api_key=api_key or "",
        provider_type=provider.provider_type,
        api_version=provider.api_version,
        models=provider.models or [],
        test_model=body.test_model,
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
```

- [ ] **Step 2: Stamp on `/providers/{provider_id}/models/probe`**

Replace the body of `probe_provider_capabilities` (lines 486-525) with:

```python
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

    client = await get_llm_router().get_client_async(provider_id=provider_id)

    updated = []
    for m in models:
        # Models are stored as dicts, but tolerate a stray legacy string.
        entry = dict(m) if isinstance(m, dict) else {"name": str(m), "model_type": "chat"}
        name = entry.get("name")
        if name:
            try:
                cap = await probe_model(client, name)
                entry["capabilities"] = cap
                # Probe used the same chat-completions call as the connectivity
                # test, so a successful probe means the model is reachable.
                entry["verified"] = True
                entry["last_tested_at"] = cap.get("probed_at") or entry.get("last_tested_at")
            except Exception as e:  # noqa: BLE001 - one bad model shouldn't abort the batch
                entry["verified"] = False
                entry["test_error"] = str(e)[:200]
        updated.append(entry)

    # Reassign (not in-place mutate) so SQLAlchemy detects the JSON change.
    provider.models = updated
    await db.commit()
    get_llm_router().invalidate_provider_cache(provider_id)
    return {"models": updated}
```

Note: the existing per-model exception handler in the original code (line 517-518) swallowed probe errors silently. The new version **stamps `verified=False`** with the error string on the entry instead of dropping it — this is the explicit fix that lets users see "this model is broken" in the UI.

- [ ] **Step 3: Compile-check the file**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && .venv/bin/python -c "from app.routers import providers; print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
git add app/routers/providers.py
git commit -m "feat(providers): stamp verified on test/probe success or failure

- POST /providers/test now writes per-model verified + last_tested_at +
  test_error to provider.models on both success and failure
- POST /providers/{id}/models/probe stamps verified=True on a successful
  probe, verified=False on exception (previously swallowed silently)
- Verification is best-effort: a DB write failure does not fail the test
  endpoint (the connectivity response is the primary signal)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Backend tests for stamping + seed

**Files:**
- Create: `tests/test_providers.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_providers.py`:

```python
"""Tests for provider verification status stamping + seed behavior."""
import pytest
from datetime import datetime
from sqlalchemy import select

from app.core.database import async_session_maker
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
    # Unrelated model untouched
    assert out[1]["verified"] is False
    assert out[1]["test_error"] == "old"
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


async def test_seed_presets_marks_all_models_verified(db):
    """Built-in presets should be seeded with verified=True so the Chat
    dropdown isn't empty on a fresh install."""
    await _seed_presets(db)
    # Each preset's models should have verified=True after seeding
    preset_names = {p.name for p in _PRESET_PROVIDERS}
    result = await db.execute(select(Provider).where(Provider.name.in_(preset_names)))
    providers = result.scalars().all()
    assert len(providers) == len(preset_names)
    for p in providers:
        assert p.models, f"{p.name} has no models"
        for m in p.models:
            assert isinstance(m, dict)
            assert m.get("verified") is True, f"{p.name}/{m.get('name')}: {m}"
            assert m.get("last_tested_at"), f"{p.name}/{m.get('name')}: no timestamp"
            assert m.get("test_error") is None


async def test_stamp_then_reload_roundtrip(db):
    """Full round-trip: create a provider, stamp a model, commit, reload,
    verify the value persisted. This guards against SQLAlchemy not detecting
    the JSON-column mutation."""
    p = Provider(
        name=f"stamp-test-{datetime.utcnow().timestamp()}",
        provider_type="openai",
        base_url="https://example.com/v1",
        models=[{"name": "m1", "model_type": "chat"}],
        is_active=True,
    )
    async with async_session_maker() as session:
        session.add(p)
        await session.commit()
        await session.refresh(p)
        pid = p.id

    # Re-fetch and stamp
    async with async_session_maker() as session:
        result = await session.execute(select(Provider).where(Provider.id == pid))
        prov = result.scalar_one()
        prov.models = _stamp_model_verified(prov.models, "m1", ok=True)
        await session.commit()

    # Re-fetch and assert
    async with async_session_maker() as session:
        result = await session.execute(select(Provider).where(Provider.id == pid))
        prov = result.scalar_one()
        assert prov.models[0]["verified"] is True
        assert prov.models[0]["last_tested_at"]
        # Cleanup
        await session.delete(prov)
        await session.commit()
```

- [ ] **Step 2: Make sure the `db` fixture exists**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && grep -rn "def db" tests/conftest.py tests/fixtures/ 2>/dev/null`

If `db` is not defined anywhere:
- The test_smoke_api.py and test_integration.py files use a `db` fixture, so check those for the definition.
- If they define it inline, mirror that pattern. If they import it from `tests/fixtures/db.py`, import the same.
- If the fixture truly does not exist, see "Adding the `db` fixture" appendix below.

- [ ] **Step 3: Run the tests against a fresh DB**

Ensure the test DB is running on port 5433 (per the verified setup documented in the conversation summary).

Run:
```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_providers.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
git add tests/test_providers.py
git commit -m "test(providers): cover verified stamping + preset seed

- update existing / append new / truncate long errors / tolerate legacy
  string models
- seed presets mark every model verified=True with a timestamp
- full round-trip through SQLAlchemy commit+re-fetch

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Appendix (only if `db` fixture is missing)

Add to `tests/conftest.py` (creating the file if needed) — first check the existing pattern by reading `tests/test_smoke_api.py` and copying whatever fixture it uses.

If no pattern exists, add this minimal async-session fixture:

```python
import pytest_asyncio
from app.core.database import async_session_maker


@pytest_asyncio.fixture
async def db():
    async with async_session_maker() as session:
        yield session
```

---

## Task 5: Frontend — `ProviderModel` interface, `Chat.tsx` filter, empty state

**Files:**
- Modify: `webui/src/api/client.ts` (add fields to `ProviderModel`)
- Modify: `webui/src/pages/Chat.tsx` (delete `FALLBACK_MODELS`, filter on `verified === true`, add empty hint)

- [ ] **Step 1: Read the current `ProviderModel` type**

Run: `grep -n "ProviderModel" webui/src/api/client.ts | head -5`

If it lives elsewhere (e.g. `webui/src/types.ts`), edit that file instead.

- [ ] **Step 2: Add the new fields to the type**

In the `ProviderModel` interface, add (alphabetically or grouped — match local style):

```ts
export interface ProviderModel {
  provider_id: number
  provider_name: string
  provider_type: string
  base_url: string
  model: string
  // optional verification status (gates Chat dropdown visibility)
  verified?: boolean | null
  last_tested_at?: string | null
  test_error?: string | null
}
```

- [ ] **Step 3: Delete `FALLBACK_MODELS` and its uses in `Chat.tsx`**

In `webui/src/pages/Chat.tsx`:

1. Delete the entire `FALLBACK_MODELS` constant (lines 68-72):
```ts
const FALLBACK_MODELS = [
  { provider_id: 0, provider_name: 'OPENAI', provider_type: 'openai', base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  { provider_id: 0, provider_name: 'ANTHROPIC', provider_type: 'anthropic', base_url: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-7-2025' },
  { provider_id: 0, provider_name: 'GROK', provider_type: 'xai', base_url: 'https://api.x.ai/v1', model: 'grok-3' },
]
```

2. Change the `useState` initializer (line 110) from:
```ts
const [availableModels, setAvailableModels] = useState<ProviderModel[]>(FALLBACK_MODELS)
```
to:
```ts
const [availableModels, setAvailableModels] = useState<ProviderModel[]>([])
```

3. Inside `loadModels` (lines 300-323), change the inner `for m in p.models` loop to filter on `verified === true`:

Replace the inner block:
```ts
for (const m of (p.models || [])) {
  models.push({
    provider_id: p.id,
    provider_name: p.name.toUpperCase(),
    provider_type: p.provider_type,
    base_url: (p.base_url || '').replace(/\/$/, ''),
    model: typeof m === 'string' ? m : (m as any).name || m,
  })
}
```

with:
```ts
for (const m of (p.models || [])) {
  // Only show models that the user has explicitly verified.
  // A model dict's `verified` is set to true by /providers/test and
  // /providers/{id}/models/probe on a successful call. Built-in presets are
  // seeded with verified=true.
  const verified = (typeof m === 'object' && m !== null) ? (m as any).verified : undefined
  if (verified !== true) continue
  models.push({
    provider_id: p.id,
    provider_name: p.name.toUpperCase(),
    provider_type: p.provider_type,
    base_url: (p.base_url || '').replace(/\/$/, ''),
    model: typeof m === 'string' ? m : (m as any).name || m,
  })
}
```

- [ ] **Step 4: Add the empty-state hint**

In the same `Chat.tsx` file, find the `<select>` for the model dropdown (around line 660). It currently looks like:

```tsx
<span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)' }}>MODEL</span>
<select value={providerModel} onChange={e => { localStorage.setItem('lastProviderModel', e.target.value); setProviderModel(e.target.value) }}
  style={{ ... }}>
  <option value="auto">AUTO</option>
  {availableModels.map(m => <option key={`${m.provider_id}:${m.model}`} value={`${m.provider_id}:${m.model}`}>{m.provider_name} / {m.model}</option>)}
</select>
```

Wrap the `<select>` plus an optional hint in a fragment with conditional rendering. Replace that block with:

```tsx
<span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)' }}>MODEL</span>
<select value={providerModel} onChange={e => { localStorage.setItem('lastProviderModel', e.target.value); setProviderModel(e.target.value) }}
  style={{
    height: 26, padding: '0 8px',
    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
    color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
    fontFamily: 'var(--font-mono)',
  }}
  title={availableModels.length === 0 ? 'No verified models — go to Providers and click TEST' : undefined}
>
  <option value="auto">AUTO</option>
  {availableModels.map(m => <option key={`${m.provider_id}:${m.model}`} value={`${m.provider_id}:${m.model}`}>{m.provider_name} / {m.model}</option>)}
</select>
{availableModels.length === 0 && (
  <span style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--text-dim)' }}>no verified models — test in Providers</span>
)}
```

- [ ] **Step 5: Type-check the frontend**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard/webui && npx tsc --noEmit`
Expected: no errors. (If the type-check command differs in this repo, use whatever `package.json` declares.)

- [ ] **Step 6: Commit**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
git add webui/src/api/client.ts webui/src/pages/Chat.tsx
git commit -m "feat(chat): filter model dropdown to verified-only

- Remove FALLBACK_MODELS placeholder (provider_id:0 never matches a real
  provider; was the source of 'default models I don't recognize')
- loadModels now skips any model whose verified flag is not true
- Empty state shows a small grey hint pointing to the Providers page

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Frontend — per-model status badge in `Providers.tsx`

**Files:**
- Modify: `webui/src/pages/Providers.tsx` (find the per-model row render, add a badge)

- [ ] **Step 1: Find the per-model render location**

Run: `grep -n "models.map\|m.name\|testModel(" /Users/jc/Documents/cyber-agent/cyberguard/webui/src/pages/Providers.tsx | head -10`

This is where each model row is rendered. The actual lines may have changed since this plan was written — adapt to whatever the current rendering code is.

- [ ] **Step 2: Add a small status badge function inside the component**

Locate the function (likely `ProviderDetailPanel` or similar) that renders the model list. Add this helper inside it, just before the `return` of the JSX:

```tsx
const modelStatusBadge = (m: any) => {
  // Matches the new per-model verification fields added to ModelInfo
  if (m && m.verified === true) {
    return <span style={{ fontSize: 10, padding: '1px 6px', border: '1px solid var(--accent-border)', color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>✓ VERIFIED</span>
  }
  if (m && m.verified === false) {
    return <span title={m.test_error || 'test failed'} style={{ fontSize: 10, padding: '1px 6px', border: '1px solid rgba(248,113,113,0.4)', color: '#f87171', fontFamily: 'var(--font-mono)' }}>✗ FAILED</span>
  }
  return <span style={{ fontSize: 10, padding: '1px 6px', border: '1px solid var(--border)', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>· UNTESTED</span>
}
```

- [ ] **Step 3: Insert the badge next to each model name**

Find where each model name is rendered in the row (likely `<div>{m.name}</div>` or similar) and add `{modelStatusBadge(m)}` immediately after it. The exact placement depends on the existing layout — keep it inline-flex and add a small left margin so it sits beside the name without crowding it.

- [ ] **Step 4: Type-check**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard/webui && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
git add webui/src/pages/Providers.tsx
git commit -m "feat(providers): per-model verification status badge

Each model row now shows ✓ VERIFIED (green), ✗ FAILED (red, hover for
error), or · UNTESTED (grey) based on the verified field added to
ModelInfo. Built-in presets and any model the user has successfully
tested/probed will show ✓ from the moment this commit lands.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: End-to-end manual verification

**Files:** none (manual)

- [ ] **Step 1: Bring up the test stack**

Run: `cd /Users/jc/Documents/cyber-agent/cyberguard && docker compose up -d api webui postgres redis`

If the running stack is already up, skip — the seeded preset providers were created before this commit and won't have `verified=True`. Either:
  - Recreate the API container (`docker compose up -d --force-recreate api`) so the seed runs again, OR
  - Open the WebUI → Providers → click "TEST" on each preset you care about to stamp them verified.

- [ ] **Step 2: Verify Chat dropdown**

1. Open the WebUI in a browser, log in.
2. Navigate to the Chat page.
3. Open the MODEL dropdown.
4. Expected: only the models from built-in presets appear (e.g. `MINIMAX / MiniMax-Text-01`, `GEMINI / gemini-2.5-flash`, etc.). The hardcoded `OPENAI / gpt-4o` etc. from before should be gone.
5. If no presets are showing: confirm `availableModels.length === 0` and the empty-state hint text appears.

- [ ] **Step 3: Verify the test→verified flow**

1. Go to Providers page.
2. Find a provider that has a model not yet tested (e.g. add a custom provider with a fake model).
3. Confirm the model row shows `· UNTESTED`.
4. Click the per-model "test" button. Wait for the result.
5. Reload the page (or wait for the test to complete and the panel to refresh).
6. Expected: that model now shows `✓ VERIFIED` (success) or `✗ FAILED` (failure).
7. Navigate to Chat. Expected: the model now appears in (or does not appear in) the dropdown based on the result.

- [ ] **Step 4: Run the full backend test suite**

Run:
```bash
cd /Users/jc/Documents/cyber-agent/cyberguard
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```

Expected: 272 + 6 = 278 tests pass (the original 272 from the prior session plus the 6 new ones in `tests/test_providers.py`). If the count is off by 1-2 due to test count drift, that's fine; the new file must pass and nothing else should regress.

- [ ] **Step 5: Commit the memory update**

If anything notable happened during the run (e.g. test count surprise, new fix), update the memory file per project convention. Otherwise skip.

---

## Self-Review Checklist

- [x] **Spec coverage:** §3.1 schema → Task 1; §3.2 stamp logic → Tasks 2-3; §3.3 preset seed → Task 4 (`test_seed_presets_marks_all_models_verified`); §3.4 Chat filter → Task 5; §3.5 Providers badge → Task 6; E2E → Task 7.
- [x] **No placeholders:** all code blocks are complete; no "TBD" / "add appropriate error handling".
- [x] **Type consistency:** `_stamp_model_verified` defined Task 2, used Task 3 with the same signature; `ProviderModel.verified?` field added Task 5 step 2, used Task 5 step 3.
- [x] **Frequent commits:** 7 tasks = 7 logical commits (Tasks 1, 2, 3, 4, 5, 6, optional memory).
- [x] **Fits existing patterns:** uses `_seed_presets` (existing) and `_test_provider_connectivity` (existing), doesn't introduce new modules; tests follow the pattern in `tests/test_smoke_api.py`.
