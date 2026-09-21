"""Governance checks that must run before direct streaming reaches an LLM."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers.chat_stream import stream_chat
from app.schemas.chat import ChatRequest


@pytest.mark.asyncio
async def test_global_kill_switch_blocks_stream_chat_before_model_access():
    with patch(
        "app.services.kill_switch.is_halted",
        new=AsyncMock(return_value=True),
    ) as halted:
        with pytest.raises(HTTPException) as error:
            await stream_chat(
                ChatRequest(message="hello"),
                current_user=SimpleNamespace(user_id=7),
            )

    assert error.value.status_code == 503
    assert "kill switch" in str(error.value.detail).lower()
    halted.assert_awaited_once_with()
