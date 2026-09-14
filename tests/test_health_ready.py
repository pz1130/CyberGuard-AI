"""Readiness must fail closed without leaking backend exception text."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse


class _FailingConnect:
    def __init__(self, message: str):
        self._message = message

    async def __aenter__(self):
        raise RuntimeError(self._message)

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_readiness_probe_returns_503_without_backend_exception_text(monkeypatch):
    secret = "password=supersecret host=internal-db"
    redis_secret = "NOAUTH Authentication required secret=preview-redis-local"

    boom_engine = MagicMock()
    boom_engine.connect.return_value = _FailingConnect(secret)
    monkeypatch.setattr("app.core.database.engine", boom_engine)
    monkeypatch.setattr(
        "app.core.ratelimit.get_redis",
        AsyncMock(side_effect=RuntimeError(redis_secret)),
    )

    from app.main import readiness_probe

    response = await readiness_probe()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    body = response.body.decode()
    assert "degraded" in body
    assert "supersecret" not in body
    assert "preview-redis-local" not in body
    assert "internal-db" not in body
    assert "NOAUTH" not in body
    payload = response.body.decode()
    assert '"postgres"' in payload
    assert '"redis"' in payload
