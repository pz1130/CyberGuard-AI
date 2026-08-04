"""Compatibility re-export — implementation lives in ``llm_router.resilience``.

M0a-1: moved out of app so packages/llm_router owns the pure routing layer.
Call sites may keep importing from here; behavior is unchanged.
"""
from llm_router.resilience import (  # noqa: F401
    acall_with_retry,
    rate_limit,
)

__all__ = ["acall_with_retry", "rate_limit"]
