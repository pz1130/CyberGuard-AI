"""Master Agent configuration service (version-cached for multi-worker)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.master_config import MasterAgentConfig
from app.core.versioned_cache import VersionedCache

# Cross-worker version-gated cache (replaces the old process-local global).
_cache: VersionedCache[MasterAgentConfig] = VersionedCache("master_config")


async def _load_or_create(db: AsyncSession) -> MasterAgentConfig:
    """Load the single config row, creating the default if absent."""
    result = await db.execute(select(MasterAgentConfig).where(MasterAgentConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        default_intent = """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Agent types: threat_intel, log_anomaly, vuln_scanner, remediation, osint, general
"""
        default_summary = "You are CyberGuard's summarizer. Create a concise summary of agent results for the user."
        default_system = "You are CyberGuard, a security operations assistant. You help users with threat analysis, vulnerability assessment, log analysis, and incident response. Be precise and actionable."
        config = MasterAgentConfig(
            id=1,
            llm_model="MiniMax-m2.7",
            temperature=0.7,
            system_prompt=default_system,
            intent_parser_prompt=default_intent,
            summarizer_prompt=default_summary,
            max_rounds=10,
            auto_approve_threshold=0,
            branding_logo=None,
            branding_company_name=None,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


async def _apply_and_refresh(db: AsyncSession, data: dict) -> MasterAgentConfig:
    """Apply `data` to the existing row, commit, and return the refreshed object."""
    config = await db.get(MasterAgentConfig, 1)
    if not config:
        return await _load_or_create(db)
    for key, value in data.items():
        if hasattr(config, key):
            setattr(config, key, value)
    await db.commit()
    await db.refresh(config)
    return config


async def get_master_config(db: AsyncSession) -> MasterAgentConfig:
    """Get master agent config, creating default if not exists (version-cached)."""
    return await _cache.get(lambda: _load_or_create(db))


async def update_master_config(db: AsyncSession, data: dict) -> MasterAgentConfig:
    """Update master agent config and bump the cross-worker cache version."""
    config = await _apply_and_refresh(db, data)
    await _cache.bump(config)
    return config


async def invalidate_cache() -> None:
    """Invalidate the cache across all workers (bumps the global version)."""
    await _cache.bump()
