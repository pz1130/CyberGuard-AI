"""Token usage tracking API."""
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user, require_role
from app.core.rbac import Role
from app.core.auth import AuthenticatedUser
from app.models.token_usage import TokenUsageLog
from app.models.provider import Provider

router = APIRouter()


class TokenUsageByModel(BaseModel):
    provider_id: str = ""
    provider_name: str = ""
    model_name: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0


class TokenUsageSummary(BaseModel):
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_calls: int = 0
    total_cost_usd: float = 0.0
    by_model: list[TokenUsageByModel] = []
    by_date: dict[str, dict] = {}


class TokenUsageRecord(BaseModel):
    id: int
    provider_id: str
    provider_name: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    call_count: int
    date_str: str
    created_at: datetime


# Model pricing (USD per 1M tokens) - common models
MODEL_PRICING = {
    # OpenAI
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    # Anthropic
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku": {"input": 0.8, "output": 4.0},
    "claude-3-opus": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet": {"input": 3.0, "output": 15.0},
    # Google
    "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    # Default
    "default": {"input": 1.0, "output": 5.0},
}


def get_model_price(model_name: str) -> dict:
    """Get pricing for a model."""
    for key, pricing in MODEL_PRICING.items():
        if key in model_name.lower():
            return pricing
    return MODEL_PRICING["default"]


def calculate_cost(prompt_tokens: int, completion_tokens: int, model_name: str) -> float:
    """Calculate cost in USD."""
    pricing = get_model_price(model_name)
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


@router.get("/token-usage/summary", response_model=TokenUsageSummary)
async def get_token_usage_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    provider_id: Optional[int] = Query(None, description="Filter by provider ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role(Role.ADMIN)),
):
    """Get aggregated token usage summary."""
    today = date.today()
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=30)
    end = date.fromisoformat(end_date) if end_date else today

    query = select(TokenUsageLog).where(
        TokenUsageLog.date_str >= start.isoformat(),
        TokenUsageLog.date_str <= end.isoformat(),
    )
    if model_name:
        query = query.where(TokenUsageLog.model_name == model_name)
    if provider_id:
        query = query.where(TokenUsageLog.provider_id == str(provider_id))

    result = await db.execute(query)
    logs = result.scalars().all()

    total_prompt = 0
    total_completion = 0
    total_calls = 0
    by_model_dict: dict[str, TokenUsageByModel] = {}
    by_date_dict: dict[str, dict] = {}

    for log in logs:
        total_prompt += log.prompt_tokens
        total_completion += log.completion_tokens
        total_calls += log.call_count

        key = f"{log.provider_id}:{log.model_name}"
        if key not in by_model_dict:
            by_model_dict[key] = TokenUsageByModel(
                provider_id=log.provider_id,
                provider_name=log.provider_name,
                model_name=log.model_name,
            )
        by_model_dict[key].prompt_tokens += log.prompt_tokens
        by_model_dict[key].completion_tokens += log.completion_tokens
        by_model_dict[key].total_tokens += log.total_tokens
        by_model_dict[key].call_count += log.call_count

        if log.date_str not in by_date_dict:
            by_date_dict[log.date_str] = {"prompt_tokens": 0, "completion_tokens": 0, "call_count": 0}
        by_date_dict[log.date_str]["prompt_tokens"] += log.prompt_tokens
        by_date_dict[log.date_str]["completion_tokens"] += log.completion_tokens
        by_date_dict[log.date_str]["call_count"] += log.call_count

    total_cost = 0.0
    for model_data in by_model_dict.values():
        total_cost += calculate_cost(
            model_data.prompt_tokens,
            model_data.completion_tokens,
            model_data.model_name,
        )

    return TokenUsageSummary(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_prompt + total_completion,
        total_calls=total_calls,
        total_cost_usd=round(total_cost, 2),
        by_model=list(by_model_dict.values()),
        by_date=by_date_dict,
    )


@router.get("/token-usage/records", response_model=list[TokenUsageRecord])
async def get_token_usage_records(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    provider_id: Optional[int] = Query(None, description="Filter by provider ID"),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role(Role.ADMIN)),
):
    """Get individual token usage records."""
    today = date.today()
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=30)
    end = date.fromisoformat(end_date) if end_date else today

    query = select(TokenUsageLog).where(
        TokenUsageLog.date_str >= start.isoformat(),
        TokenUsageLog.date_str <= end.isoformat(),
    ).order_by(TokenUsageLog.date_str.desc(), TokenUsageLog.id.desc()).limit(limit)

    if model_name:
        query = query.where(TokenUsageLog.model_name == model_name)
    if provider_id:
        query = query.where(TokenUsageLog.provider_id == str(provider_id))

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        TokenUsageRecord(
            id=log.id,
            provider_id=log.provider_id,
            provider_name=log.provider_name,
            model_name=log.model_name,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            total_tokens=log.total_tokens,
            call_count=log.call_count,
            date_str=log.date_str,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get("/token-usage/providers", response_model=list[dict])
async def get_providers_with_usage(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role(Role.ADMIN)),
):
    """Get list of providers with usage data."""
    result = await db.execute(
        select(
            TokenUsageLog.provider_id,
            TokenUsageLog.provider_name,
            func.sum(TokenUsageLog.total_tokens).label("total_tokens"),
            func.sum(TokenUsageLog.call_count).label("total_calls"),
        ).group_by(
            TokenUsageLog.provider_id,
            TokenUsageLog.provider_name,
        ).order_by(func.sum(TokenUsageLog.total_tokens).desc())
    )
    rows = result.all()
    return [
        {
            "provider_id": row.provider_id,
            "provider_name": row.provider_name,
            "total_tokens": row.total_tokens or 0,
            "total_calls": row.total_calls or 0,
        }
        for row in rows
    ]
