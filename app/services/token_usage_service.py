"""Token usage recording service."""
from datetime import date
from sqlalchemy import select, func
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
        today = date.today().isoformat()

        # Check if there's an existing record for today with same provider+model
        result = await db.execute(
            select(TokenUsageLog).where(
                TokenUsageLog.provider_id == str(provider_id),
                TokenUsageLog.model_name == model_name,
                TokenUsageLog.date_str == today,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.prompt_tokens += prompt_tokens
            existing.completion_tokens += completion_tokens
            existing.total_tokens += total_tokens
            existing.call_count += 1
        else:
            log = TokenUsageLog(
                provider_id=str(provider_id),
                provider_name=provider_name,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                call_count=1,
                date_str=today,
            )
            db.add(log)

        await db.commit()

    @staticmethod
    async def get_provider_name(db: AsyncSession, provider_id: int) -> str:
        """Get provider name by ID."""
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = result.scalar_one_or_none()
        return provider.name if provider else f"Provider-{provider_id}"
