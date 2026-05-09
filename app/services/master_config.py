"""Master Agent configuration service."""
import json
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.master_config import MasterAgentConfig

# In-memory cache for config (refreshed on update)
_config_cache: Optional[MasterAgentConfig] = None


async def get_master_config(db: AsyncSession) -> MasterAgentConfig:
    """Get master agent config, creating default if not exists."""
    global _config_cache

    # Try cache first
    if _config_cache is not None:
        return _config_cache

    result = await db.execute(select(MasterAgentConfig).where(MasterAgentConfig.id == 1))
    config = result.scalar_one_or_none()

    if config is None:
        # Create default config
        default_intent = """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, group_chat, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Agent types: threat_intel, log_anomaly, vuln_scanner, remediation, compliance, osint, general
"""
        default_summary = "You are CyberGuard's summarizer. Create a concise summary of agent results for the user."
        default_system = "You are CyberGuard, a security operations assistant. You help users with threat analysis, vulnerability assessment, log analysis, and security compliance. Be precise and actionable."

        config = MasterAgentConfig(
            id=1,
            model="MiniMax-m2.7",
            temperature=0.7,
            system_prompt=default_system,
            intent_parser_prompt=default_intent,
            summarizer_prompt=default_summary,
            max_rounds=10,
            auto_approve_threshold=0,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

    _config_cache = config
    return config


async def update_master_config(db: AsyncSession, data: dict) -> MasterAgentConfig:
    """Update master agent config and invalidate cache."""
    global _config_cache

    # Fetch fresh instance within current session (don't use cache for updates)
    config = await db.get(MasterAgentConfig, 1)
    if not config:
        return await get_master_config(db)

    for key, value in data.items():
        if hasattr(config, key) and value is not None:
            setattr(config, key, value)

    await db.commit()
    await db.refresh(config)
    _config_cache = config
    return config


def invalidate_cache():
    """Invalidate the in-memory cache."""
    global _config_cache
    _config_cache = None