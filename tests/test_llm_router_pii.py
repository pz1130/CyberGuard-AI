"""Tests for PII guard in the LLM router."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services.llm_router import LLMRouter
from app.core.pii import SecretsDetectedError


def _resp(text="ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None),
                                 finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))


@pytest.mark.asyncio
async def test_chat_redacts_pii_before_create():
    r = LLMRouter()
    captured = {}
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(side_effect=lambda **kw: captured.update(kw) or _resp()))))
    with patch.object(r, "get_client_async", AsyncMock(return_value=fake_client)), \
         patch.object(r, "_record_token_usage", AsyncMock()), \
         patch.object(r, "_load_master_config", AsyncMock(return_value={})), \
         patch("app.config.settings.MOCK_MODE", False):
        await r.chat([{"role": "user", "content": "email me at a@b.com"}], provider_id=1)
    sent = captured["messages"][-1]["content"]
    assert "a@b.com" not in sent and "[REDACTED_EMAIL]" in sent


@pytest.mark.asyncio
async def test_chat_blocks_secrets():
    r = LLMRouter()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_resp()))))
    with patch.object(r, "get_client_async", AsyncMock(return_value=fake_client)), \
         patch.object(r, "_load_master_config", AsyncMock(return_value={})), \
         patch("app.config.settings.MOCK_MODE", False):
        with pytest.raises(SecretsDetectedError):
            await r.chat([{"role": "user", "content": "use key AKIAIOSFODNN7EXAMPLE"}],
                         provider_id=1)
