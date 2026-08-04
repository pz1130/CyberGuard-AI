"""Pure LLM routing primitives — no agent concepts, no app.* imports.

M0a-1: resilience + utils. M0a-2: thinking levels + cache_control helpers.
Business methods (parse_intent, generate_summary, build_chat_system_prompt)
stay in ``app.services.llm_router``.
"""

from llm_router.cache_control import apply_prompt_cache_key, mark_system_for_cache
from llm_router.resilience import acall_with_retry, rate_limit
from llm_router.thinking import apply_thinking_to_kwargs, normalize_thinking_level
from llm_router.utils import extract_json_object, model_name, strip_think_blocks

__all__ = [
    "acall_with_retry",
    "rate_limit",
    "model_name",
    "strip_think_blocks",
    "extract_json_object",
    "apply_thinking_to_kwargs",
    "normalize_thinking_level",
    "mark_system_for_cache",
    "apply_prompt_cache_key",
]
