"""Five-step tool policy pipeline (INV-28).

    prepare_arguments → validate_arguments → before_tool_call → execute → after_tool_call

* ``before_tool_call`` may block (returns a result, skips execute).
* ``after_tool_call`` may rewrite / redact the result.
* Audit is a *separate* mechanism (see ``events.py``); hooks here must not be
  used as a fire-and-forget audit channel.

M0a-1: ``validate_arguments`` default is pass-through. Real schema validation
lands in M0a-2 (INV-30). Existing argv/schema checks may still live inside
``execute`` until then — behavior unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Mapping, MutableMapping, Optional


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
    # Filled by stages
    prepared_arguments: Optional[Dict[str, Any]] = None
    validated_arguments: Optional[Dict[str, Any]] = None
    result: Any = None
    blocked: bool = False
    block_reason: str = ""


# Hook callables — all async for a uniform await surface.
PrepareFn = Callable[[ToolCallContext], Awaitable[Dict[str, Any]]]
ValidateFn = Callable[[ToolCallContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]
BeforeFn = Callable[[ToolCallContext, Dict[str, Any]], Awaitable[Optional[BlockedResult]]]
ExecuteFn = Callable[[ToolCallContext, Dict[str, Any]], Awaitable[Any]]
AfterFn = Callable[[ToolCallContext, Any], Awaitable[Any]]


async def _identity_prepare(ctx: ToolCallContext) -> Dict[str, Any]:
    return dict(ctx.arguments)


async def _identity_validate(_ctx: ToolCallContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """M0a-1 pass-through — schema validation is M0a-2 (INV-30)."""
    return args


async def _identity_before(
    _ctx: ToolCallContext, _args: Dict[str, Any]
) -> Optional[BlockedResult]:
    return None


async def _identity_after(_ctx: ToolCallContext, result: Any) -> Any:
    return result


@dataclass
class PipelineHooks:
    """Per-call or per-backend hook set. Defaults preserve behavior (no-ops)."""

    prepare_arguments: PrepareFn = _identity_prepare
    validate_arguments: ValidateFn = _identity_validate
    before_tool_call: BeforeFn = _identity_before
    execute: Optional[ExecuteFn] = None
    after_tool_call: AfterFn = _identity_after


class ToolPipeline:
    """Runs the five stages in order. All tool execution should go through this."""

    def __init__(self, hooks: PipelineHooks):
        if hooks.execute is None:
            raise ValueError("PipelineHooks.execute is required")
        self.hooks = hooks

    async def run(self, ctx: ToolCallContext) -> Any:
        args = await self.hooks.prepare_arguments(ctx)
        ctx.prepared_arguments = args

        args = await self.hooks.validate_arguments(ctx, args)
        ctx.validated_arguments = args

        blocked = await self.hooks.before_tool_call(ctx, args)
        if blocked is not None:
            ctx.blocked = True
            ctx.block_reason = blocked.reason
            ctx.result = blocked.payload
            return blocked.payload

        result = await self.hooks.execute(ctx, args)  # type: ignore[misc]
        result = await self.hooks.after_tool_call(ctx, result)
        ctx.result = result
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
) -> Any:
    """Convenience entry: build context + hooks and run the pipeline.

    Prefer this (or ``ToolPipeline.run``) over calling backend executors directly
    so static checks can prove every path is gated (INV-28).
    """
    hooks = PipelineHooks(
        prepare_arguments=prepare_arguments or _identity_prepare,
        validate_arguments=validate_arguments or _identity_validate,
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
    return await ToolPipeline(hooks).run(ctx)
