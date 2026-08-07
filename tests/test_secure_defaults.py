"""Fail-closed defaults and sub-agent transport security."""
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.services import agent_executor as ae


_KEYS = {"ENCRYPTION_KEY": "a" * 64, "SECRET_KEY": "b" * 64}


def _settings(**overrides):
    return Settings(**{**_KEYS, **overrides})


# ---- fail-closed defaults ---------------------------------------------------

def test_auto_approve_is_off_by_default():
    """A security product must not approve its own privileged actions."""
    assert _settings().AUTO_APPROVE is False


def test_insecure_transport_flags_are_off_by_default():
    s = _settings()
    assert s.SUB_AGENT_ALLOW_INSECURE_HTTP is False
    assert s.ALLOW_PLAINTEXT_AGENT_API_KEY is False


@pytest.mark.parametrize("flag", [
    "AUTO_APPROVE",
    "SUB_AGENT_ALLOW_INSECURE_HTTP",
    "ALLOW_PLAINTEXT_AGENT_API_KEY",
])
def test_production_refuses_insecure_flags(flag):
    """Previously AUTO_APPROVE only warned outside development. A warning nobody
    reads is the same as no control."""
    with pytest.raises(ValueError, match=flag):
        _settings(ENVIRONMENT="production", **{flag: True})


def test_development_may_opt_in():
    s = _settings(ENVIRONMENT="development", AUTO_APPROVE=True,
                  SUB_AGENT_ALLOW_INSECURE_HTTP=True)
    assert s.AUTO_APPROVE is True


# ---- sub-agent transport ----------------------------------------------------

def test_http_endpoint_is_refused():
    """Requests carry the agent's decrypted env vars in the body."""
    with patch.object(ae.settings, "SUB_AGENT_ALLOW_INSECURE_HTTP", False):
        with pytest.raises(ValueError, match="https"):
            ae.require_secure_endpoint("http://agent.example.com")


def test_https_endpoint_is_accepted():
    with patch.object(ae.settings, "SUB_AGENT_ALLOW_INSECURE_HTTP", False):
        assert ae.require_secure_endpoint(
            "https://agent.example.com") == "https://agent.example.com"


def test_http_allowed_when_explicitly_opted_in():
    with patch.object(ae.settings, "SUB_AGENT_ALLOW_INSECURE_HTTP", True):
        assert ae.require_secure_endpoint("http://agent.example.com")


@pytest.mark.asyncio
async def test_execute_refuses_plaintext_endpoint_before_sending_credentials():
    w = ae.SubAgentWrapper.__new__(ae.SubAgentWrapper)
    w.agent_id, w.agent_name = 1, "remote"
    w.endpoint_url = "http://agent.example.com"
    w.env_vars = {"OPENCLAW_API_KEY": "super-secret"}
    w.timeout, w.max_retries = 5, 3

    client = AsyncMock()
    client.post = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ae.settings, "SUB_AGENT_ALLOW_INSECURE_HTTP", False), \
         patch.object(ae.httpx, "AsyncClient", return_value=client):
        result = await w.execute(task="t")

    assert result["status"] == "error"
    assert "https" in result["error"]
    client.post.assert_not_awaited()          # secret never left the process


# ---- plaintext API key ------------------------------------------------------

def test_plaintext_api_key_is_refused_by_default():
    cfg = {"agent_name": "legacy", "metadata_json": {"api_key": "plain-secret"}}
    with patch.object(ae.settings, "ALLOW_PLAINTEXT_AGENT_API_KEY", False):
        assert ae._resolve_api_key(cfg) == ""


def test_plaintext_api_key_allowed_when_opted_in():
    cfg = {"agent_name": "legacy", "metadata_json": {"api_key": "plain-secret"}}
    with patch.object(ae.settings, "ALLOW_PLAINTEXT_AGENT_API_KEY", True):
        assert ae._resolve_api_key(cfg) == "plain-secret"


def test_encrypted_key_is_preferred_and_unaffected():
    from app.core.security import encrypt_data
    cfg = {"agent_name": "modern",
           "metadata_json": {"api_key_encrypted": encrypt_data("enc-secret"),
                             "api_key": "plain-secret"}}
    with patch.object(ae.settings, "ALLOW_PLAINTEXT_AGENT_API_KEY", False):
        assert ae._resolve_api_key(cfg) == "enc-secret"
