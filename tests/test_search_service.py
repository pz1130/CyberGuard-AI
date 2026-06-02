"""Tests for the pluggable search-provider layer (app/services/search_service.py).

All network calls are isolated in each provider's `_fetch`, so these tests use
fake providers / monkeypatched `_fetch` and never touch the network.
"""
import pytest

from app.services.search_service import (
    SearchResult, SearchProvider, SearchService,
    DuckDuckGoProvider, SploitusProvider, build_providers,
)


class FakeProvider(SearchProvider):
    name = "fake"
    category = "web"

    def __init__(self):
        self.calls = 0

    async def _fetch(self, query, limit):
        self.calls += 1
        return [SearchResult(title=f"r-{query}", url="http://x", snippet="s",
                             source=self.name, extra={})]


def test_build_providers_from_csv_ignores_unknown():
    provs = build_providers("duckduckgo, sploitus, , bogus")
    by_name = {p.name: p for p in provs}
    assert set(by_name) == {"duckduckgo", "sploitus"}     # bogus/blank dropped
    assert by_name["duckduckgo"].category == "web"
    assert by_name["sploitus"].category == "vuln"


def test_duckduckgo_parser_maps_fields():
    raw = [{"title": "Nginx docs", "href": "http://nginx.org", "body": "web server"}]
    out = DuckDuckGoProvider()._parse(raw)
    assert out == [SearchResult(title="Nginx docs", url="http://nginx.org",
                                snippet="web server", source="duckduckgo", extra={})]


def test_sploitus_parser_maps_exploit_fields():
    raw = {"exploits": [{
        "title": "Log4Shell RCE", "href": "http://sploitus/1",
        "source": "github", "score": 9.8, "type": "exploit",
        "published": "2021-12-10"}]}
    out = SploitusProvider()._parse(raw)
    assert len(out) == 1
    r = out[0]
    assert r.title == "Log4Shell RCE" and r.url == "http://sploitus/1"
    assert r.source == "sploitus"
    assert r.extra["score"] == 9.8 and r.extra["type"] == "exploit"


class VulnProvider(SearchProvider):
    name = "vp"
    category = "vuln"

    async def _fetch(self, query, limit):
        return [SearchResult(title="exploit", url="http://e", snippet="",
                             source=self.name, extra={"score": 7})]


class BoomProvider(SearchProvider):
    name = "boom"
    category = "web"

    async def _fetch(self, query, limit):
        raise RuntimeError("network down")


@pytest.mark.asyncio
async def test_search_routes_by_category():
    web, vuln = FakeProvider(), VulnProvider()
    svc = SearchService(providers=[web, vuln], cache_ttl=300)

    vres = await svc.vuln_search("log4j")
    assert [r.source for r in vres] == ["vp"]   # only the vuln provider
    assert web.calls == 0                        # web provider untouched


@pytest.mark.asyncio
async def test_failing_provider_is_skipped_not_fatal():
    good, bad = FakeProvider(), BoomProvider()
    svc = SearchService(providers=[bad, good], cache_ttl=300)

    out = await svc.web_search("nginx")
    assert [r.source for r in out] == ["fake"]   # boom skipped, good survives


@pytest.mark.asyncio
async def test_web_search_returns_results_and_caches():
    prov = FakeProvider()
    svc = SearchService(providers=[prov], cache_ttl=300)

    out1 = await svc.web_search("nginx", limit=5)
    out2 = await svc.web_search("nginx", limit=5)

    assert [r.title for r in out1] == ["r-nginx"]
    assert out2 == out1
    assert prov.calls == 1                       # second call served from cache
