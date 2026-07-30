"""M0a-1: packages/agent_core boundary, pipeline, Operations, audit bus."""
import ast
import inspect
from pathlib import Path

import pytest

from agent_core import (
    AuditBus,
    AuditEvent,
    AuditLayer,
    AuditPhase,
    BlockedResult,
    OperationsBundle,
    PipelineHooks,
    ToolCallContext,
    ToolPipeline,
    run_tool_call,
)
from agent_core.pipeline import ToolPipeline as TP


_PKG = Path(__file__).resolve().parents[1] / "packages" / "agent_core"
_FORBIDDEN_ROOTS = ("app", "sqlalchemy", "redis", "celery", "fastapi", "langgraph")


def _iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        yield p


def test_agent_core_package_has_no_forbidden_imports():
    offenders = []
    for path in _iter_py_files(_PKG):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _FORBIDDEN_ROOTS:
                        offenders.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in _FORBIDDEN_ROOTS:
                    offenders.append(f"{path.name}: from {node.module}")
    assert not offenders, "forbidden imports in agent_core:\n" + "\n".join(offenders)


@pytest.mark.asyncio
async def test_pipeline_happy_path_order():
    order = []

    async def prepare(ctx):
        order.append("prepare")
        return {**ctx.arguments, "p": 1}

    async def validate(ctx, args):
        order.append("validate")
        return args

    async def before(ctx, args):
        order.append("before")
        return None

    async def execute(ctx, args):
        order.append("execute")
        return {"ok": True, "args": args}

    async def after(ctx, result):
        order.append("after")
        return {**result, "tagged": True}

    out = await ToolPipeline(
        PipelineHooks(
            prepare_arguments=prepare,
            validate_arguments=validate,
            before_tool_call=before,
            execute=execute,
            after_tool_call=after,
        )
    ).run(ToolCallContext(tool_name="t", arguments={"a": 1}))

    assert order == ["prepare", "validate", "before", "execute", "after"]
    assert out == {"ok": True, "args": {"a": 1, "p": 1}, "tagged": True}


@pytest.mark.asyncio
async def test_pipeline_before_blocks_execute():
    executed = False

    async def before(ctx, args):
        return BlockedResult(payload={"status": "denied"}, reason="nope")

    async def execute(ctx, args):
        nonlocal executed
        executed = True
        return {"status": "completed"}

    out = await run_tool_call(
        tool_name="t",
        arguments={},
        before_tool_call=before,
        execute=execute,
    )
    assert out == {"status": "denied"}
    assert executed is False


@pytest.mark.asyncio
async def test_validate_arguments_default_is_passthrough():
    """M0a-1: no schema rejection at validate stage."""

    async def execute(ctx, args):
        return args

    out = await run_tool_call(
        tool_name="t",
        arguments={"anything": "goes", "n": 1},
        execute=execute,
    )
    assert out == {"anything": "goes", "n": 1}


@pytest.mark.asyncio
async def test_audit_bus_awaits_subscribers_in_order():
    seen = []

    async def s1(ev):
        seen.append(("s1", ev.phase.value))

    async def s2(ev):
        seen.append(("s2", ev.phase.value))

    bus = AuditBus()
    bus.subscribe(s1)
    bus.subscribe(s2)
    await bus.emit(
        AuditEvent(layer=AuditLayer.TOOL_EXECUTION, phase=AuditPhase.START, name="x")
    )
    assert seen == [("s1", "start"), ("s2", "start")]


@pytest.mark.asyncio
async def test_audit_bus_propagates_subscriber_errors():
    async def bad(ev):
        raise RuntimeError("audit write failed")

    bus = AuditBus()
    bus.subscribe(bad)
    with pytest.raises(RuntimeError, match="audit write failed"):
        await bus.emit(
            AuditEvent(layer=AuditLayer.TURN, phase=AuditPhase.END, name="t")
        )


def test_operations_bundle_defaults_none():
    b = OperationsBundle()
    assert b.read is None and b.exec is None and b.edit is None


def test_execute_tool_source_uses_run_tool_call():
    """Chokepoint: pool tools must enter the policy pipeline (INV-28)."""
    import app.services.tool_executor as te

    src = inspect.getsource(te.execute_tool)
    assert "run_tool_call" in src


def test_internal_dispatch_source_uses_run_tool_call():
    """Agent tool branches must enter the policy pipeline (INV-28)."""
    import app.services.internal_agent as ia

    src = inspect.getsource(ia.InternalAgentRunner._dispatch)
    assert "run_tool_call" in src
