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
    estimated_cost_usd: Optional[float] = None


class TokenUsageSummary(BaseModel):
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_calls: int = 0
    total_cost_usd: float = 0.0
    priced_tokens: int = 0
    unpriced_tokens: int = 0
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


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    """Calculate estimated USD cost from administrator-configured prices."""
    input_cost = (prompt_tokens / 1_000_000) * input_price_per_million
    output_cost = (completion_tokens / 1_000_000) * output_price_per_million
    return input_cost + output_cost


def get_configured_model_price(provider: Provider, model_name: str) -> Optional[tuple[float, float]]:
    """Return configured input/output prices for an exact provider model."""
    for model in provider.models or []:
        if not isinstance(model, dict) or model.get("name") != model_name:
            continue
        input_price = model.get("input_price_per_million")
        output_price = model.get("output_price_per_million")
        if input_price is None or output_price is None:
            return None
        return float(input_price), float(output_price)
    return None


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

    numeric_provider_ids = {
        int(model_data.provider_id)
        for model_data in by_model_dict.values()
        if model_data.provider_id.isdigit() and int(model_data.provider_id) > 0
    }
    providers_by_id: dict[int, Provider] = {}
    if numeric_provider_ids:
        provider_result = await db.execute(
            select(Provider).where(Provider.id.in_(numeric_provider_ids))
        )
        providers_by_id = {provider.id: provider for provider in provider_result.scalars().all()}

    total_cost = 0.0
    priced_tokens = 0
    unpriced_tokens = 0
    for model_data in by_model_dict.values():
        provider = providers_by_id.get(int(model_data.provider_id)) if model_data.provider_id.isdigit() else None
        pricing = get_configured_model_price(provider, model_data.model_name) if provider else None
        if pricing is None:
            unpriced_tokens += model_data.total_tokens
            continue
        model_data.estimated_cost_usd = round(calculate_cost(
            model_data.prompt_tokens,
            model_data.completion_tokens,
            pricing[0],
            pricing[1],
        ), 6)
        total_cost += model_data.estimated_cost_usd
        priced_tokens += model_data.total_tokens

    return TokenUsageSummary(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_prompt + total_completion,
        total_calls=total_calls,
        total_cost_usd=round(total_cost, 6),
        priced_tokens=priced_tokens,
        unpriced_tokens=unpriced_tokens,
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
