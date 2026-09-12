"""Token usage recording service."""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_usage import TokenUsageLog
from app.models.provider import Provider


class TokenUsageService:
    """Service for recording and querying token usage."""

    @staticmethod
    async def record_usage(
        db: AsyncSession,
        provider_id: int,
        provider_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        """Record token usage for a single LLM call."""
        # Keep one row per call. The read APIs already aggregate rows, and inserts
        # avoid lost updates when multiple workers finish requests concurrently.
        db.add(TokenUsageLog(
            provider_id=str(provider_id),
            provider_name=provider_name,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            call_count=1,
            date_str=date.today().isoformat(),
        ))

        await db.commit()

    @staticmethod
    async def get_provider_name(db: AsyncSession, provider_id: int) -> str:
        """Get provider name by ID."""
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
        return provider.name if provider else f"Provider-{provider_id}"
