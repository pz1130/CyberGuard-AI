"""Pluggable search-provider layer for OSINT / vulnerability recon.

Exposes a small provider abstraction (`SearchProvider`) and a `SearchService`
facade with a short in-memory TTL cache. v1 ships DuckDuckGo (general web) and
Sploitus (exploit/vuln). The internal-agent tool loop surfaces these as the
synthetic tools `web_search` / `vuln_search`. See:
  docs/superpowers/specs/2026-06-02-pluggable-search-providers-design.md

Design rules:
  * Each provider isolates its real network call in `_fetch`; the public
    `search()` wraps it so any failure degrades to `[]` instead of raising
    into the agent.
  * `SearchService` skips a failing/empty provider rather than failing the
    whole search.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str                       # provider name that produced this hit
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet,
                "source": self.source, **({"extra": self.extra} if self.extra else {})}


class SearchProvider:
    """Base class. Subclasses set `name`/`category` and implement `_fetch`."""

    name: str = "base"
    category: str = "web"             # "web" | "vuln"

    async def search(self, query: str, *, limit: int = 5) -> List[SearchResult]:
        """Public entry: never raises — failures degrade to an empty list."""
        if not query or not query.strip():
            return []
        try:
            return await self._fetch(query.strip(), limit)
        except Exception as e:           # noqa: BLE001 - providers must not crash the agent
            logger.warning("search provider %s failed for %r: %s", self.name, query, e)
            return []

    async def _fetch(self, query: str, limit: int) -> List[SearchResult]:
        raise NotImplementedError


class SearchService:
    """Facade over a set of providers with a short per-(provider,query) cache."""

    def __init__(self, providers: List[SearchProvider], *, cache_ttl: int = 300):
        self.providers = providers
        self.cache_ttl = cache_ttl
        self._cache: Dict[tuple, tuple[float, List[SearchResult]]] = {}

    async def _provider_search(self, prov: SearchProvider, query: str,
                               limit: int) -> List[SearchResult]:
        key = (prov.name, query, limit)
        hit = self._cache.get(key)
        now = time.monotonic()
        if hit and hit[0] > now:
            return hit[1]
        results = await prov.search(query, limit=limit)
        self._cache[key] = (now + self.cache_ttl, results)
        return results

    async def _search_category(self, category: str, query: str,
                               limit: int) -> List[SearchResult]:
        merged: List[SearchResult] = []
        for prov in self.providers:
            if prov.category != category:
                continue
            merged.extend(await self._provider_search(prov, query, limit))
        return merged

    async def web_search(self, query: str, limit: int = 5) -> List[SearchResult]:
        return await self._search_category("web", query, limit)

    async def vuln_search(self, query: str, limit: int = 5) -> List[SearchResult]:
        return await self._search_category("vuln", query, limit)


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------

# Browser-like UA — Sploitus (and many search endpoints) reject default clients.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class DuckDuckGoProvider(SearchProvider):
    """General web recon via the `ddgs` library (lazily imported)."""

    name = "duckduckgo"
    category = "web"

    def _parse(self, raw: List[Dict[str, Any]]) -> List[SearchResult]:
        out = []
        for item in raw or []:
            out.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("href", "") or item.get("url", ""),
                snippet=item.get("body", "") or item.get("snippet", ""),
                source=self.name, extra={}))
        return out

    def _raw(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Blocking ddgs call, isolated so tests can monkeypatch it."""
        from ddgs import DDGS  # lazy: optional dependency
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=limit))

    async def _fetch(self, query: str, limit: int) -> List[SearchResult]:
        import asyncio
        raw = await asyncio.to_thread(self._raw, query, limit)
        return self._parse(raw)


class SploitusProvider(SearchProvider):
    """Exploit / vulnerability search via the Sploitus JSON endpoint (no key)."""

    name = "sploitus"
    category = "vuln"
    endpoint = "https://sploitus.com/search"

    def _parse(self, data: Dict[str, Any]) -> List[SearchResult]:
        out = []
        for ex in (data or {}).get("exploits", []):
            out.append(SearchResult(
                title=ex.get("title", ""),
                url=ex.get("href", ""),
                snippet=ex.get("source", ""),
                source=self.name,
                extra={k: ex.get(k) for k in ("score", "type", "published")
                       if ex.get(k) is not None}))
        return out

    async def _fetch(self, query: str, limit: int) -> List[SearchResult]:
        import httpx
        payload = {"type": "exploits", "sort": "default", "query": query,
                   "title": False, "offset": 0}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(self.endpoint, json=payload,
                                  headers={"User-Agent": _UA,
                                           "Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
        return self._parse(data)[:limit]


PROVIDER_REGISTRY: Dict[str, type] = {
    DuckDuckGoProvider.name: DuckDuckGoProvider,
    SploitusProvider.name: SploitusProvider,
}


def build_providers(names_csv: str) -> List[SearchProvider]:
    """Instantiate providers named in a csv string; unknown/blank names dropped."""
    out: List[SearchProvider] = []
    for raw in (names_csv or "").split(","):
        name = raw.strip().lower()
        cls = PROVIDER_REGISTRY.get(name)
        if cls:
            out.append(cls())
        elif name:
            logger.warning("unknown search provider %r ignored", name)
    return out


_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Process-wide singleton built from SEARCH_PROVIDERS / SEARCH_CACHE_TTL env."""
    global _search_service
    if _search_service is None:
        names = os.environ.get("SEARCH_PROVIDERS", "duckduckgo,sploitus")
        ttl = int(os.environ.get("SEARCH_CACHE_TTL", "300"))
        _search_service = SearchService(build_providers(names), cache_ttl=ttl)
    return _search_service
