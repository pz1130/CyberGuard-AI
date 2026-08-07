"""Tests for SubAgentWrapper's remote-call retry behaviour."""
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.services import agent_executor as ae
from app.services.agent_executor import SubAgentWrapper


def _wrapper(max_retries=3):
    w = SubAgentWrapper.__new__(SubAgentWrapper)
    w.agent_id = 1
    w.agent_name = "remote-ir"
    w.backend_type = "custom"
    w.endpoint_url = "https://agent.example.com"
    w.env_vars_encrypted = None
    w.env_vars = {}
    w.timeout = 5
    w.max_retries = max_retries
    return w


@pytest.mark.asyncio
async def test_connect_failures_back_off_between_attempts():
    """Retries must wait; previously they fired back-to-back within
    milliseconds, hammering an already-failing sub-agent."""
    w = _wrapper(max_retries=3)
    sleeps = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ae.asyncio, "sleep", record_sleep), \
         patch.object(ae.httpx, "AsyncClient", return_value=client):
        result = await w.execute(task="t")

    assert result["status"] == "failed"
    assert client.post.await_count == 3
    # One sleep between attempts (not after the last), exponentially growing.
    assert sleeps == [
        ae.RETRY_BACKOFF_BASE_SECONDS,
        ae.RETRY_BACKOFF_BASE_SECONDS * 2,
    ]


@pytest.mark.asyncio
async def test_success_on_first_attempt_does_not_sleep():
    w = _wrapper(max_retries=3)
    sleeps = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    response = AsyncMock()
    response.status_code = 200
    response.json = lambda: {"output": "done", "execution_time": 1.2}

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ae.asyncio, "sleep", record_sleep), \
         patch.object(ae.httpx, "AsyncClient", return_value=client):
        result = await w.execute(task="t")

    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert sleeps == []


@pytest.mark.asyncio
async def test_auth_failure_returns_immediately_without_retrying():
    """401 is terminal — retrying it just burns time."""
    w = _wrapper(max_retries=3)

    response = AsyncMock()
    response.status_code = 401

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ae.httpx, "AsyncClient", return_value=client):
        result = await w.execute(task="t")

    assert result["status"] == "error"
    assert client.post.await_count == 1
