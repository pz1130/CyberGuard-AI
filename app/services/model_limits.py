"""App-side helpers for model context_window / max_output_tokens.

Delegates catalog logic to the reusable ``agent_core.model_limits`` package.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from agent_core.model_limits import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
    enrich_model_entry,
    enrich_models_list,
    lookup_model_limits,
    resolve_model_limits,
)


async def limits_for_provider_model(
    provider_id: Optional[int],
    model_name: Optional[str],
) -> Tuple[int, int]:
    """Load provider.models from DB (if possible) and resolve limits.

    Falls back to catalog-only resolution when DB is unavailable.
    """
    models: Optional[List[Any]] = None
    if provider_id:
        try:
            from app.core.database import get_db_context
            from sqlalchemy import select
            from app.models.provider import Provider

            async with get_db_context() as session:
                row = await session.execute(
                    select(Provider.models).where(Provider.id == provider_id)
                )
                models = row.scalar_one_or_none()
        except Exception:
            models = None
    return resolve_model_limits(model_name, models)


__all__ = [
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "lookup_model_limits",
    "resolve_model_limits",
    "enrich_model_entry",
    "enrich_models_list",
    "limits_for_provider_model",
]
