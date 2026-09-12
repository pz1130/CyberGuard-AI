"""DELETE /agents/halt must not be captured as DELETE /agents/{agent_id}."""
from starlette.routing import Match

from app.main import app


def _first_full_match(method: str, path: str):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("test", 50000),
        "server": ("test", 80),
    }
    for route in app.router.routes:
        match, _child = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", None) or str(route)
    return None


def test_delete_agents_halt_matches_static_halt_route():
    path = _first_full_match("DELETE", "/api/v1/agents/halt")
    assert path is not None
    assert "{agent_id}" not in path
    assert path.endswith("/agents/halt") or path.endswith("/kill-switch")


def test_post_agents_halt_matches_static_halt_route():
    path = _first_full_match("POST", "/api/v1/agents/halt")
    assert path is not None
    assert "{agent_id}" not in path


def test_kill_switch_alias_is_registered():
    path = _first_full_match("DELETE", "/api/v1/kill-switch")
    assert path is not None
    assert path.endswith("/kill-switch")
