"""Seeded demo tools must be executable and have a rollback for contain_hard."""
from app.services.demo_catalog import DEMO_SKILLS, DEMO_TOOLS, demo_tool_by_name


def test_demo_tools_include_observe_and_contain():
    names = {t["name"] for t in DEMO_TOOLS}
    assert "simulate_observe" in names
    assert "simulate_block_ip" in names


def test_block_ip_is_governed_executable():
    tool = demo_tool_by_name("simulate_block_ip")
    assert "{ip}" in tool["command_template"]
    assert tool["rollback_command_template"]
    assert "{ip}" in tool["rollback_command_template"]
    assert tool["action_category"] == "contain_hard"
    assert tool["risk_tier"] == "high"
    assert tool["requires_approval"] is True
    assert "echo" in tool["command_template"]
    assert "SIMULATED" in tool["command_template"]


def test_observe_tool_does_not_require_approval():
    tool = demo_tool_by_name("simulate_observe")
    assert tool["action_category"] == "observe"
    assert tool["requires_approval"] is False
    assert tool["command_template"].startswith("echo")


def test_demo_skill_mentions_block_tool():
    skill = DEMO_SKILLS[0]
    assert "simulate_block_ip" in skill["md_content"]
