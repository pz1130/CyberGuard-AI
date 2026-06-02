# Pluggable Search Providers (OSINT search layer)

**Date:** 2026-06-02
**Status:** Approved → implementation
**Branch / PR:** `feat/pluggable-search-providers` (PR #7)

## Motivation

Borrowed from PentAGI's multi-engine search integration. Our OSINT-style agents
currently can't *search* anything: the built-in `osint` type in
`local_executor.py` is a single LLM call with no tool loop, and the
internal-agent loop only exposes `kb_search`. This adds a small, extensible
search-provider abstraction and wires it into the internal-agent tool loop so a
configured agent can do real web recon and vulnerability/exploit lookups.

v1 implements **DuckDuckGo** (general web) and **Sploitus** (exploit/vuln). The
abstraction is designed so Tavily / Searxng / Perplexity drop in later without
touching callers.

## Architecture

### New module: `app/services/search_service.py`

- `SearchResult` dataclass: `title, url, snippet, source, extra: dict`.
  `extra` carries provider-specific fields (e.g. Sploitus score/type/published).
- `SearchProvider` ABC:
  - `name: str`, `category: str` (`"web"` | `"vuln"`)
  - `async search(query: str, *, limit: int = 5) -> list[SearchResult]`
  - Each provider isolates its actual network call in one small overridable
    method (`_fetch`) so tests never hit the network and failures degrade to
    `[]` rather than raising into the agent.
- Concrete providers (v1):
  - `DuckDuckGoProvider` (category `web`) — via the `ddgs` library, imported
    lazily; missing lib / network error → log + `[]`.
  - `SploitusProvider` (category `vuln`) — `httpx` POST to the Sploitus JSON
    search endpoint with a browser User-Agent; parses exploit hits into
    `SearchResult`s. No API key required.
- `SearchService`:
  - Builds the enabled-provider registry from config.
  - Short **in-memory TTL cache** keyed by `(provider_name, query, limit)`;
    default TTL 300 s (`SEARCH_CACHE_TTL`).
  - `async web_search(query, limit)` / `async vuln_search(query, limit)` — fan
    out to providers of that category, merge, and cache. A failing provider is
    skipped (logged), never failing the whole search.
- `get_search_service()` module-level singleton accessor (mirrors
  `get_knowledge_service`).

### Config

- `SEARCH_PROVIDERS` env (csv; default `"duckduckgo,sploitus"`).
- `SEARCH_CACHE_TTL` env (seconds; default `300`).
- `_resolve_key(provider_name)` hook reads future paid-provider API keys from
  env / the `EnvVar` secret store. Unused by v1 (DDG + Sploitus need no key) but
  present so Tavily/Searxng wire in without caller changes.

### Internal-agent integration (`internal_agent.py`)

- New agent-config flag `enable_search` (read from `metadata_json.enable_search`
  or a top-level `enable_search` key). **No DB migration.**
- `_build_tools`: when `enable_search`, append two synthetic function tools,
  mirroring the existing `kb_search` pattern:
  - `web_search{query, limit}`
  - `vuln_search{query, limit}`
- `_dispatch`: route `web_search` / `vuln_search` to a module-level
  `search_service` instance (monkeypatchable in tests, like `knowledge_service`),
  returning JSON-serialized results.
- The loop guard + tool-call budget already built apply unchanged.
- An "OSINT agent" is then a configured internal agent with
  `enable_search: true`. The built-in `local_executor` osint prompt gets a
  one-line note that these tools exist (no behavior change to that path).

## Data flow

```
agent LLM → tool_call web_search/vuln_search
  → InternalAgentRunner._dispatch
    → search_service.web_search / vuln_search
      → TTL cache hit?  → return cached
      → else providers[category].search() (fan out)
        → provider._fetch() (ddgs / httpx)  → parse → [SearchResult]
      → merge + cache
  → JSON string back to the model as the tool result
```

## Error handling

- Provider `_fetch` failures (network, missing lib, parse error) → log +
  return `[]`; `SearchService` skips that provider.
- If *all* providers for a category fail/return nothing, the tool result is an
  empty list (not an error) so the agent can proceed / answer.
- No user-supplied URLs reach httpx (fixed provider hosts) → no SSRF surface.

## Testing (TDD, mocked — no network)

- `search_service`:
  - registry built from `SEARCH_PROVIDERS` config.
  - TTL cache: second identical call within TTL does not re-invoke the provider.
  - `web_search` / `vuln_search` route to the correct category.
  - provider parse functions tested against captured sample payloads.
  - a raising provider is skipped, not fatal.
- `internal_agent`:
  - `_build_tools` includes `web_search`/`vuln_search` iff `enable_search`.
  - `_dispatch` routes those tools to a fake `search_service`.

## Dependencies

- Add `ddgs` to `pyproject` (graceful if absent). Sploitus reuses `httpx`.

## Out of scope (YAGNI for v1)

- Tavily / Searxng / Perplexity implementations (abstraction only).
- Redis-backed cache.
- Result re-ranking / dedup beyond simple merge.
- New DB tables or migrations.
- Adding a tool loop to `LocalAgentExecutor`.
