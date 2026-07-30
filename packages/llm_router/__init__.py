"""Pure LLM routing primitives — no agent concepts, no app.* imports.

M0a-1: package boundary for chat/stream/embed resilience and helpers.
Business methods (parse_intent, generate_summary, build_chat_system_prompt)
stay in ``app.services.llm_router``.
"""

from llm_router.resilience import acall_with_retry, rate_limit
from llm_router.utils import extract_json_object, model_name, strip_think_blocks

__all__ = [
    "acall_with_retry",
    "rate_limit",
    "model_name",
    "strip_think_blocks",
    "extract_json_object",
]
