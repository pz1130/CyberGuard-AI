"""The per-agent switch for model-authored code execution."""
from __future__ import annotations

from app.models.agent import AgentConfig


def test_agent_config_has_the_mode_column():
    assert "code_execution_mode" in AgentConfig.__table__.columns


def test_mode_defaults_to_approval_so_nothing_opens_silently():
    col = AgentConfig.__table__.columns["code_execution_mode"]
    assert col.default.arg == "approval"
    assert col.server_default.arg == "approval"
    assert col.nullable is False
