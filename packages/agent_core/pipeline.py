"""Five-step tool policy pipeline (INV-28).

    prepare_arguments → validate_arguments → before_tool_call → execute → after_tool_call

M0a-2: default ``validate_arguments`` runs schema validation when an
``input_schema`` is available on the tool / metadata (INV-30).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Mapping, MutableMapping, Optional, TYPE_CHECKING

from agent_core.schema_validate import (
    SchemaValidationError,
    schema_from_tool,
    validate_tool_arguments,
)

if TYPE_CHECKING:
    from agent_core.events import AuditBus


@dataclass
class BlockedResult:
    """Returned by ``before_tool_call`` (or pipeline) when execution is refused."""

    payload: Any
    reason: str = ""


@dataclass
class ToolCallContext:
    """Mutable bag carried across pipeline stages for a single tool invocation."""

    tool_name: str
    arguments: Dict[str, Any]
    tool: Any = None
    user_id: Optional[int] = None
    metadata: MutableMapping[str, Any] = field(default_factory=dict)
    prepared_arguments: Optional[Dict[str, Any]] = None
    validated_arguments: Optional[Dict[str, Any]] = None
    result: Any = None
    blocked: bool = False
    block_reason: str = ""


PrepareFn = Callable[[ToolCallContext], Awaitable[Dict[str, Any]]]
ValidateFn = Callable[[ToolCallContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]
BeforeFn = Callable[[ToolCallContext, Dict[str, Any]], Awaitable[Optional[BlockedResult]]]
ExecuteFn = Callable[[ToolCallContext, Dict[str, Any]], Awaitable[Any]]
AfterFn = Callable[[ToolCallContext, Any], Awaitable[Any]]


async def _identity_prepare(ctx: ToolCallContext) -> Dict[str, Any]:
    return dict(ctx.arguments)


async def default_validate_arguments(
    ctx: ToolCallContext, args: Dict[str, Any]
) -> Dict[str, Any]:
    """INV-30: validate against tool input_schema when present.

    Schema sources (first hit wins):
      1. ``ctx.metadata['input_schema']``
      2. ``schema_from_tool(ctx.tool)``
    No schema → pass-through.
    """
    schema = ctx.metadata.get("input_schema")
    if schema is None:
        schema = schema_from_tool(ctx.tool)
    try:
        return validate_tool_arguments(args, schema)
    except SchemaValidationError:
        raise


async def _identity_before(
    _ctx: ToolCallContext, _args: Dict[str, Any]
) -> Optional[BlockedResult]:
    return None


async def _identity_after(_ctx: ToolCallContext, result: Any) -> Any:
    return result


@dataclass
class PipelineHooks:
    """Per-call or per-backend hook set."""

    prepare_arguments: PrepareFn = _identity_prepare
    validate_arguments: ValidateFn = default_validate_arguments
    before_tool_call: BeforeFn = _identity_before
    execute: Optional[ExecuteFn] = None
    after_tool_call: AfterFn = _identity_after


class ToolPipeline:
    """Runs the five stages in order. All tool execution should go through this."""

    def __init__(self, hooks: PipelineHooks, audit_bus: Optional["AuditBus"] = None):
        if hooks.execute is None:
            raise ValueError("PipelineHooks.execute is required")
        self.hooks = hooks
        self.audit_bus = audit_bus

    async def run(self, ctx: ToolCallContext) -> Any:
        from agent_core.events import AuditLayer, AuditPhase, emit_audit

        await emit_audit(
            self.audit_bus,
            layer=AuditLayer.TOOL_EXECUTION,
            phase=AuditPhase.START,
            name=ctx.tool_name,
            payload={"arguments": dict(ctx.arguments)},
            tool_call_id=str(ctx.metadata.get("tool_call_id") or "") or None,
            agent_run_id=str(ctx.metadata.get("agent_run_id") or "") or None,
        )

        args = await self.hooks.prepare_arguments(ctx)
        ctx.prepared_arguments = args

        try:
            args = await self.hooks.validate_arguments(ctx, args)
        except SchemaValidationError as exc:
            payload = {
                "status": "error",
                "error": exc.message,
                "is_error": True,
            }
            ctx.blocked = True
            ctx.block_reason = "schema_validation"
            ctx.result = payload
            await emit_audit(
                self.audit_bus,
                layer=AuditLayer.TOOL_EXECUTION,
                phase=AuditPhase.END,
                name=ctx.tool_name,
                payload={"blocked": True, "reason": "schema_validation",
                         "error": exc.message},
                tool_call_id=str(ctx.metadata.get("tool_call_id") or "") or None,
                agent_run_id=str(ctx.metadata.get("agent_run_id") or "") or None,
            )
            return payload
        ctx.validated_arguments = args

        blocked = await self.hooks.before_tool_call(ctx, args)
        if blocked is not None:
            ctx.blocked = True
            ctx.block_reason = blocked.reason
            ctx.result = blocked.payload
            await emit_audit(
                self.audit_bus,
                layer=AuditLayer.TOOL_EXECUTION,
                phase=AuditPhase.END,
                name=ctx.tool_name,
                payload={"blocked": True, "reason": blocked.reason},
                tool_call_id=str(ctx.metadata.get("tool_call_id") or "") or None,
                agent_run_id=str(ctx.metadata.get("agent_run_id") or "") or None,
            )
            return blocked.payload

        result = await self.hooks.execute(ctx, args)  # type: ignore[misc]
        result = await self.hooks.after_tool_call(ctx, result)
        ctx.result = result
        await emit_audit(
            self.audit_bus,
            layer=AuditLayer.TOOL_EXECUTION,
            phase=AuditPhase.END,
            name=ctx.tool_name,
            payload={"blocked": False},
            tool_call_id=str(ctx.metadata.get("tool_call_id") or "") or None,
            agent_run_id=str(ctx.metadata.get("agent_run_id") or "") or None,
        )
        return result


async def run_tool_call(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    execute: ExecuteFn,
    tool: Any = None,
    user_id: Optional[int] = None,
    metadata: Optional[MutableMapping[str, Any]] = None,
    prepare_arguments: Optional[PrepareFn] = None,
    validate_arguments: Optional[ValidateFn] = None,
    before_tool_call: Optional[BeforeFn] = None,
    after_tool_call: Optional[AfterFn] = None,
    audit_bus: Optional["AuditBus"] = None,
) -> Any:
    """Convenience entry: build context + hooks and run the pipeline."""
    hooks = PipelineHooks(
        prepare_arguments=prepare_arguments or _identity_prepare,
        validate_arguments=validate_arguments or default_validate_arguments,
        before_tool_call=before_tool_call or _identity_before,
        execute=execute,
        after_tool_call=after_tool_call or _identity_after,
    )
    ctx = ToolCallContext(
        tool_name=tool_name,
        arguments=dict(arguments),
        tool=tool,
        user_id=user_id,
        metadata=metadata if metadata is not None else {},
    )
    return await ToolPipeline(hooks, audit_bus=audit_bus).run(ctx)
