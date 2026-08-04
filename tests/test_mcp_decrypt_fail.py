"""MCP env decrypt fails closed with RuntimeError (INV-25)."""
from __future__ import annotations

import pytest

from app.services import mcp_executor as me


def test_decrypt_env_raises_when_ciphertext_unreadable(monkeypatch):
    class S:
        name = "siem"
        env_vars_encrypted = "cipher"

    def boom(_):
        raise ValueError("bad")

    monkeypatch.setattr(me, "decrypt_data", boom)
    with pytest.raises(RuntimeError, match="cannot decrypt"):
        me._decrypt_env(S())


def test_decrypt_env_empty_when_no_ciphertext():
    class S:
        name = "x"
        env_vars_encrypted = None

    assert me._decrypt_env(S()) == {}
