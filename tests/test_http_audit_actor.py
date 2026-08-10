"""The HTTP audit trail must name the actor and the outcome.

Every row this middleware wrote used to be `user_id=None` with the method and
path hashed into `input_hash` — an audit trail that cannot answer "who did
this" or "did it succeed", which are the only two questions anyone asks of one.
Two causes: the middleware runs before dependencies resolve so it never saw the
authenticated user, and it logged before `call_next` so it never saw the
status. The AuditLog model already had ip_address / user_agent / request_path /
metadata_json columns; nothing wrote them.
"""
from __future__ import annotations

import pytest

import app.main as app_main


class _StubURL:
    def __init__(self, path):
        self.path = path


class _StubClient:
    host = "203.0.113.9"


class _StubState:
    pass


class _StubRequest:
    def __init__(self, path="/api/v1/agents", method="GET", user_id=None, username=None):
        self.url = _StubURL(path)
        self.method = method
        self.client = _StubClient()
        self.headers = {"user-agent": "pytest-agent/1.0"}
        self.state = _StubState()
        if user_id is not None:
            self.state.user_id = user_id
            self.state.username = username


class _StubResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.fixture
def recorded(monkeypatch):
    """Capture what the middleware hands to log_audit."""
    calls = []

    async def _fake_log_audit(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(app_main, "log_audit", _fake_log_audit)
    return calls


async def _run(request, response=None, raises=None):
    async def call_next(_req):
        if raises is not None:
            raise raises
        return response or _StubResponse()

    return await app_main.audit_middleware(request, call_next)


@pytest.mark.asyncio
async def test_an_authenticated_request_records_who_made_it(recorded):
    await _run(_StubRequest(user_id=42, username="analyst"))

    assert len(recorded) == 1
    entry = recorded[0]
    assert entry["user_id"] == 42
    assert entry["metadata"]["username"] == "analyst"


@pytest.mark.asyncio
async def test_an_anonymous_request_records_no_actor(recorded):
    await _run(_StubRequest())
    assert recorded[0]["user_id"] is None


@pytest.mark.asyncio
async def test_the_outcome_is_recorded_not_just_the_attempt(recorded):
    await _run(_StubRequest(), response=_StubResponse(403))
    assert recorded[0]["metadata"]["status_code"] == 403
    assert recorded[0]["output_data"]["status_code"] == 403


@pytest.mark.asyncio
async def test_client_ip_path_and_user_agent_are_stored_queryably(recorded):
    """These go in real columns, not into the input/output hash."""
    await _run(_StubRequest(path="/api/v1/skills"))
    entry = recorded[0]
    assert entry["ip_address"] == "203.0.113.9"
    assert entry["user_agent"] == "pytest-agent/1.0"
    assert entry["request_path"] == "/api/v1/skills"


@pytest.mark.asyncio
async def test_a_failed_request_is_still_audited(recorded):
    """An exception must not be a way to leave no trace."""
    boom = RuntimeError("handler exploded")
    with pytest.raises(RuntimeError):
        await _run(_StubRequest(), raises=boom)

    assert len(recorded) == 1
    assert recorded[0]["metadata"]["status_code"] == 500


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json"])
async def test_probe_endpoints_stay_out_of_the_audit_trail(recorded, path):
    """Liveness probes would otherwise bury the signal."""
    await _run(_StubRequest(path=path))
    assert recorded == []


# --- the writer must actually persist the new columns ------------------------


@pytest.mark.asyncio
async def test_log_audit_carries_the_queryable_fields_through():
    from app.core.audit import log_audit

    entry = await log_audit(
        user_id=7,
        agent_id=None,
        action="GET /api/v1/agents",
        input_data={"a": 1},
        output_data={"status_code": 200},
        ip_address="198.51.100.4",
        user_agent="curl/8",
        request_path="/api/v1/agents",
        metadata={"status_code": 200, "username": "root"},
    )

    assert entry["user_id"] == 7
    assert entry["ip_address"] == "198.51.100.4"
    assert entry["user_agent"] == "curl/8"
    assert entry["request_path"] == "/api/v1/agents"
    assert entry["metadata"]["username"] == "root"
    # payloads stay hashed — they are tamper evidence, not query material
    assert len(entry["input_hash"]) == 64


@pytest.mark.asyncio
async def test_overlong_user_agent_cannot_overflow_its_column():
    from app.core.audit import log_audit

    entry = await log_audit(
        user_id=None,
        agent_id=None,
        action="GET /x",
        input_data={},
        output_data={},
        user_agent="A" * 5000,
        request_path="/" + "b" * 5000,
    )
    assert len(entry["user_agent"]) == 500
    assert len(entry["request_path"]) == 500


def test_login_names_the_actor_but_only_when_it_succeeds():
    """The login row is the one that matters most for credential attacks.

    It predates any get_current_user call, so the endpoint has to record the
    actor itself. A *failed* attempt must not: there is no authenticated user,
    and its 401 plus source IP is the signal.
    """
    from fastapi.testclient import TestClient

    import app.main as main_module

    captured = []
    real = main_module.log_audit

    async def spy(**kwargs):
        captured.append(kwargs)
        return await real(**kwargs)

    main_module.log_audit = spy
    try:
        with TestClient(main_module.app) as client:
            ok = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin123"},
            )
            if ok.status_code != 200:
                pytest.skip("seeded admin credentials unavailable in this environment")
            client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "definitely-wrong"},
            )
    finally:
        main_module.log_audit = real

    logins = [c for c in captured if c["request_path"] == "/api/v1/auth/login"]
    assert len(logins) == 2
    succeeded, failed = logins

    assert succeeded["metadata"]["status_code"] == 200
    assert succeeded["user_id"] is not None
    assert succeeded["metadata"]["username"] == "admin"

    assert failed["metadata"]["status_code"] == 401
    assert failed["user_id"] is None


def test_the_dependency_records_the_actor_on_request_state():
    """get_current_user is the only place that knows who the caller is."""
    import inspect

    from app.core.dependencies import get_current_user

    source = inspect.getsource(get_current_user)
    assert "request.state.user_id" in source
    assert "request: Request" in source
