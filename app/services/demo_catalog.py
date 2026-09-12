"""Built-in demo tools/skills so a fresh install has an executable path.

Commands are `echo SIMULATED ...` — they go through the isolated tool-runner
but do not touch real infrastructure.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DEMO_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "simulate_observe",
        "description": "Demo observe tool. Echoes a message via the tool-runner.",
        "category": "observe",
        "permission_level": "low",
        "action_category": "observe",
        "risk_tier": "low",
        "requires_approval": False,
        "is_active": True,
        "command_template": "echo {msg}",
        "rollback_command_template": None,
        "input_schema_json": (
            '{"type":"object","properties":{"msg":{"type":"string"}},'
            '"required":["msg"]}'
        ),
        "timeout_seconds": 15,
        "md_content": "Safe demo observe tool. Prints the message. No side effects.",
        "tags": ["demo", "observe"],
    },
    {
        "name": "simulate_block_ip",
        "description": (
            "Demo contain_hard tool. Prints a simulated deny for {ip}. "
            "Requires human approval and has a rollback echo."
        ),
        "category": "containment",
        "permission_level": "high",
        "action_category": "contain_hard",
        "risk_tier": "high",
        "requires_approval": True,
        "is_active": True,
        "command_template": "echo SIMULATED deny ip host {ip}",
        "rollback_command_template": "echo SIMULATED allow ip host {ip}",
        "input_schema_json": (
            '{"type":"object","properties":{"ip":{"type":"string"}},'
            '"required":["ip"]}'
        ),
        "timeout_seconds": 15,
        "md_content": (
            "Simulated edge ACL deny. Does not talk to a firewall. "
            "Use for RC approval/tool-runner demonstrations."
        ),
        "tags": ["demo", "contain_hard"],
    },
]

DEMO_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "demo_containment",
        "description": "How to use the simulated containment tools in a demo.",
        "category": "remediation",
        "permission_level": "high",
        "requires_approval": True,
        "is_active": True,
        "md_content": (
            "# Demo containment\n\n"
            "Use `simulate_observe` for read-only checks.\n"
            "Use `simulate_block_ip` with argument `ip` for a high-risk "
            "containment that must pause for human approval. "
            "The tool-runner only echoes `SIMULATED deny ip host <ip>`.\n"
        ),
        "tags": ["demo", "containment"],
    },
]

DEMO_AGENT_NAME = "demo_remediation"


def demo_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    for tool in DEMO_TOOLS:
        if tool["name"] == name:
            return tool
    return None


async def seed_demo_catalog_on_startup() -> None:
    """Idempotent: insert demo tools/skill/agent if missing."""
    from sqlalchemy import select

    from app.core.database import get_db_context
    from app.models.agent import AgentConfig
    from app.models.provider import Provider
    from app.models.skill import Skill, Tool

    async with get_db_context() as session:
        tool_ids: Dict[str, int] = {}
        for spec in DEMO_TOOLS:
            existing = await session.execute(select(Tool).where(Tool.name == spec["name"]))
            row = existing.scalar_one_or_none()
            if row is None:
                row = Tool(**spec)
                session.add(row)
                await session.flush()
            tool_ids[spec["name"]] = row.id

        for spec in DEMO_SKILLS:
            existing = await session.execute(select(Skill).where(Skill.name == spec["name"]))
            if existing.scalar_one_or_none() is None:
                session.add(Skill(**spec))

        existing_agent = await session.execute(
            select(AgentConfig).where(AgentConfig.agent_name == DEMO_AGENT_NAME)
        )
        if existing_agent.scalar_one_or_none() is None:
            provider_id = None
            providers = await session.execute(
                select(Provider).where(Provider.is_active.is_(True)).order_by(Provider.id)
            )
            for p in providers.scalars().all():
                if p.api_key_encrypted:
                    provider_id = p.id
                    break
            session.add(AgentConfig(
                agent_name=DEMO_AGENT_NAME,
                kind="internal",
                backend_type="internal",
                description="Demo remediation agent bound to simulated containment tools.",
                system_prompt=(
                    "You are a demo remediation agent. For containment, call "
                    "simulate_block_ip with the target IP. Do not claim a real "
                    "firewall change; the tool only echoes a SIMULATED deny."
                ),
                is_active=True,
                permission_level="high",
                autonomy_tier="L2",
                allowed_categories=["observe", "annotate", "contain_hard", "remediate"],
                governed=True,
                llm_provider_id=provider_id,
                associated_tools=[
                    tool_ids[n] for n in ("simulate_observe", "simulate_block_ip")
                    if n in tool_ids
                ],
                associated_skills=None,
            ))
        await session.commit()
