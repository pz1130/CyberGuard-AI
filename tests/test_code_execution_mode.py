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


import pytest
from fastapi import HTTPException

from app.routers.agents import CODE_EXECUTION_MODES, validate_code_execution_mode


def test_the_three_modes_are_the_only_ones_accepted():
    assert CODE_EXECUTION_MODES == ("off", "approval", "auto")
    for mode in CODE_EXECUTION_MODES:
        assert validate_code_execution_mode(mode) == mode


def test_an_unknown_mode_is_refused():
    with pytest.raises(HTTPException, match="code_execution_mode"):
        validate_code_execution_mode("yolo")


def test_none_means_leave_it_alone():
    assert validate_code_execution_mode(None) is None
