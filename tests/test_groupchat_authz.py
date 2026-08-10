"""Group-chat endpoints must be authenticated and owner-scoped.

Every endpoint under /groupchat/sessions either exposes a full agent transcript
or drives real multi-agent LLM execution. Five of them shipped with no
authentication dependency at all, so an unauthenticated caller could read other
users' transcripts, inject messages into a privileged agent context, and run
rounds at the deployment's expense.

These tests assert the property structurally (every route carries an auth
dependency) rather than by mocking the service, so a future endpoint added to
this router cannot regress the guarantee unnoticed.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute


def _groupchat_routes():
    from app.main import app

    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and "/groupchat/" in r.path
    ]


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            names.add(getattr(dep.call, "__name__", str(dep.call)))
        stack.extend(dep.dependencies)
    return names


def test_the_router_is_actually_mounted():
    """Guard against this suite passing vacuously if the router is renamed."""
    routes = _groupchat_routes()
    assert len(routes) >= 6, f"expected the groupchat endpoints, got {routes}"


@pytest.mark.parametrize(
    "path_suffix",
    ["", "/message", "/round", "/complete"],
)
def test_session_scoped_endpoints_require_authentication(path_suffix):
    target = "/groupchat/sessions/{session_id}" + path_suffix
    routes = [r for r in _groupchat_routes() if r.path.endswith(target)]
    assert routes, f"no route matching {target}"
    for route in routes:
        names = _dependency_names(route)
        assert any(
            "current_user" in n or "role_checker" in n or "permission_checker" in n
            for n in names
        ), f"{route.methods} {route.path} has no auth dependency: {sorted(names)}"


def test_no_groupchat_route_is_anonymous():
    """Catch-all: covers DELETE and anything added later."""
    anonymous = []
    for route in _groupchat_routes():
        names = _dependency_names(route)
        if not any(
            "current_user" in n or "role_checker" in n or "permission_checker" in n
            for n in names
        ):
            anonymous.append(f"{sorted(route.methods)} {route.path}")
    assert anonymous == [], f"anonymous groupchat routes: {anonymous}"


@pytest.mark.asyncio
async def test_a_session_belonging_to_another_user_is_not_readable():
    """Authentication alone is not enough — sessions are owner-scoped."""
    from fastapi import HTTPException

    from app.routers.groupchat import _load_owned_session

    class _Session:
        user_id = 7

    class _Service:
        async def load_session(self, _sid):
            return _Session()

    class _User:
        user_id = 8  # a different, also-authenticated user

    with pytest.raises(HTTPException) as ei:
        await _load_owned_session(_Service(), "s1", _User())
    # 404 rather than 403: the API must not confirm the session id exists.
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_the_owner_can_still_load_their_own_session():
    from app.routers.groupchat import _load_owned_session

    class _Session:
        user_id = 7

    class _Service:
        async def load_session(self, _sid):
            return _Session()

    class _User:
        user_id = 7

    assert await _load_owned_session(_Service(), "s1", _User()) is not None
