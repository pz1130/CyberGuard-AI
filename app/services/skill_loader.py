"""Skill loading service — loads skills from DB and builds system prompts."""
from typing import Optional
from app.core.database import get_db_context
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SkillLoader:
    """Dynamically loads active skills from DB and builds LLM system prompts."""

    @staticmethod
    async def load_skills_for_agent_type(
        agent_type: str, session: Optional[AsyncSession] = None
    ) -> str:
        """
        Load all active skills matching agent_type and concatenate their md_content.

        Returns empty string if no skills found (caller should fall back to default prompt).
        """
        from app.models.skill import Skill

        if session is not None:
            return await SkillLoader._load_from_session(session, agent_type)

        async with get_db_context() as session:
            return await SkillLoader._load_from_session(session, agent_type)

    @staticmethod
    async def _load_from_session(session: AsyncSession, agent_type: str) -> str:
        from app.models.skill import Skill

        result = await session.execute(
            select(Skill).where(
                Skill.category == agent_type,
                Skill.is_active == True,
            )
        )
        skills = result.scalars().all()

        if not skills:
            return ""

        parts = [
            f"# {skill.name} (v{skill.version})\n\n{skill.md_content}"
            for skill in skills
        ]
        return "\n\n---\n\n".join(parts)

    @staticmethod
    async def load_all_active_skills(
        session: Optional[AsyncSession] = None,
    ) -> dict[str, str]:
        """
        Load all active skills grouped by category.

        Returns dict mapping category -> concatenated md_content.
        """
        from app.models.skill import Skill

        if session is not None:
            return await SkillLoader._load_all_from_session(session)

        async with get_db_context() as session:
            return await SkillLoader._load_all_from_session(session)

    @staticmethod
    async def _load_all_from_session(session: AsyncSession) -> dict[str, str]:
        from app.models.skill import Skill

        result = await session.execute(
            select(Skill).where(Skill.is_active == True)
        )
        skills = result.scalars().all()

        grouped: dict[str, list[str]] = {}
        for skill in skills:
            cat = skill.category or "general"
            grouped.setdefault(cat, []).append(
                f"# {skill.name} (v{skill.version})\n\n{skill.md_content}"
            )

        return {
            cat: "\n\n---\n\n".join(parts)
            for cat, parts in grouped.items()
        }

    @staticmethod
    async def get_skill_by_name(name: str) -> Optional[str]:
        """Load a specific skill by name, returning its md_content."""
        from app.models.skill import Skill

        async with get_db_context() as session:
            result = await session.execute(
                select(Skill).where(Skill.name == name, Skill.is_active == True)
            )
            skill = result.scalar_one_or_none()
            return skill.md_content if skill else None
