"""Deployment-agnostic agent kernel primitives (M0a-1/M0a-2).

No ``app.*``, sqlalchemy, redis, celery, or fastapi imports.
"""

from agent_core.compact import maybe_compact_messages
from agent_core.compressor import (
    SUMMARY_PROMPT,
    build_summary_user_message,
    compress_history,
    maybe_compress,
    select_window,
)
from agent_core.tokens import estimate_tokens, remaining_budget
from agent_core.schema_validate import SchemaValidationError, validate_tool_arguments
from agent_core.tool_result import ToolResult, normalize_tool_result
from agent_core.events import (
    AuditBus,
    AuditEvent,
    AuditLayer,
    AuditPhase,
    emit_audit,
    get_default_audit_bus,
)
from agent_core.loop_utils import (
    AUTO_CONTINUE_MAX,
    CONTEXT_COMPACT_CHARS,
    CONTEXT_KEEP_RECENT,
    LLM_RETRY_BACKOFF,
    LLM_RETRY_MAX,
    LOOP_DETECT_THRESHOLD,
    REFLECT_GUIDANCE,
    REFLECT_MAX,
    TOOL_CALL_BUDGET_DEFAULT,
    TOOL_CALL_BUDGET_LIMITED,
    TOOL_RESULT_MAX_CHARS,
    budget_notice,
    estimate_message_chars,
    loop_notice,
    messages_to_text,
    tool_call_fingerprint,
    truncate_tool_result,
)
from agent_core.operations import (
    EditOperations,
    ExecOperations,
    OperationsBundle,
    ReadOperations,
)
from agent_core.pipeline import (
    BlockedResult,
    PipelineHooks,
    ToolCallContext,
    ToolPipeline,
    run_tool_call,
)
from agent_core.run_loop import RunLoopConfig, run_loop

__all__ = [
    "ReadOperations",
    "ExecOperations",
    "EditOperations",
    "OperationsBundle",
    "ToolCallContext",
    "PipelineHooks",
    "ToolPipeline",
    "BlockedResult",
    "run_tool_call",
    "AuditBus",
    "AuditEvent",
    "AuditLayer",
    "AuditPhase",
    "emit_audit",
    "get_default_audit_bus",
    "estimate_tokens",
    "remaining_budget",
    "select_window",
    "build_summary_user_message",
    "compress_history",
    "maybe_compress",
    "SUMMARY_PROMPT",
    "maybe_compact_messages",
    "tool_call_fingerprint",
    "loop_notice",
    "budget_notice",
    "truncate_tool_result",
    "estimate_message_chars",
    "messages_to_text",
    "RunLoopConfig",
    "run_loop",
    "SchemaValidationError",
    "validate_tool_arguments",
    "ToolResult",
    "normalize_tool_result",
    "TOOL_RESULT_MAX_CHARS",
    "AUTO_CONTINUE_MAX",
    "CONTEXT_COMPACT_CHARS",
    "CONTEXT_KEEP_RECENT",
    "LOOP_DETECT_THRESHOLD",
    "REFLECT_MAX",
    "LLM_RETRY_MAX",
    "LLM_RETRY_BACKOFF",
    "TOOL_CALL_BUDGET_DEFAULT",
    "TOOL_CALL_BUDGET_LIMITED",
    "REFLECT_GUIDANCE",
]
