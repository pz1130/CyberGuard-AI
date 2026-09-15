"""Agent connectivity checks must handle PostgreSQL's naive UTC timestamps."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.time import utc_now
from app.routers.agents import test_agent_connection as check_agent_connection


@pytest.mark.asyncio
async def test_openclaw_connection_accepts_naive_last_seen():
    agent = SimpleNamespace(
        kind="external",
        backend_type="openclaw",
        api_key_hash="configured",
        openclaw_last_seen=utc_now() - timedelta(seconds=10),
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: agent)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    response = await check_agent_connection(1, db, None)

    assert response.success is True


@pytest.mark.asyncio
async def test_internal_agent_connection_is_english():
    provider = SimpleNamespace(id=34, name="MiniMax", is_active=True)
    agent = SimpleNamespace(
        kind="internal",
        llm_provider_id=34,
        backend_type="openclaw",
    )
    replies = [
        SimpleNamespace(scalar_one_or_none=lambda: agent),
        SimpleNamespace(scalar_one_or_none=lambda: provider),
    ]

    async def execute(_stmt):
        return replies.pop(0)

    db = SimpleNamespace(execute=execute)
    response = await check_agent_connection(1, db, None)
    assert response.success is True
    assert "Ready" in response.error
    assert "in-process" in response.error
    assert "就绪" not in response.error
    assert "进程内" not in response.error
