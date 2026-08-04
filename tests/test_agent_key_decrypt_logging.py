"""API key decrypt failures must not be silent (INV-25)."""
from __future__ import annotations

import logging

from app.services.agent_executor import _resolve_api_key


def test_decrypt_env_failure_logs_and_continues(caplog, monkeypatch):
    def boom(_data):
        raise ValueError("bad key material")

    monkeypatch.setattr("app.services.agent_executor.decrypt_data", boom)
    with caplog.at_level(logging.ERROR):
        key = _resolve_api_key(
            {
                "agent_name": "oc1",
                "env_vars_encrypted": "cipher-blob",
                "metadata_json": {"api_key": "plain-fallback"},
            }
        )
    assert key == "plain-fallback"
    assert any("decrypt" in r.message.lower() for r in caplog.records)


def test_decrypt_meta_failure_logs(caplog, monkeypatch):
    def boom(_data):
        raise ValueError("bad")

    monkeypatch.setattr("app.services.agent_executor.decrypt_data", boom)
    with caplog.at_level(logging.ERROR):
        key = _resolve_api_key(
            {
                "agent_name": "oc2",
                "metadata_json": {"api_key_encrypted": "blob"},
            }
        )
    assert key == ""
    assert any("api_key_encrypted" in r.message for r in caplog.records)
