"""Audit event bus — pure observation, separate from the policy pipeline (INV-29).

Subscribers cannot veto or mutate events. ``emit`` awaits each subscriber in
order; a raised exception propagates (must not be swallowed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional


class AuditLayer(str, Enum):
    AGENT = "agent"
    TURN = "turn"
    MESSAGE = "message"
    TOOL_EXECUTION = "tool_execution"


class AuditPhase(str, Enum):
    START = "start"
    UPDATE = "update"
    END = "end"


@dataclass(frozen=True)
class AuditEvent:
    layer: AuditLayer
    phase: AuditPhase
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    # Correlation ids (opaque to the bus)
    agent_run_id: Optional[str] = None
    turn_id: Optional[str] = None
    tool_call_id: Optional[str] = None


Subscriber = Callable[[AuditEvent], Awaitable[None]]


class AuditBus:
    """In-process ordered subscriber list. Not a network bus."""

    def __init__(self) -> None:
        self._subscribers: List[Subscriber] = []

    def subscribe(self, handler: Subscriber) -> None:
        self._subscribers.append(handler)

    def clear(self) -> None:
        self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def emit(self, event: AuditEvent) -> None:
        """Await every subscriber in registration order.

        Must be awaited by callers. Fire-and-forget is a security hole (INV-29).
        """
        for handler in self._subscribers:
            await handler(event)


# Process-default bus: empty until app/desktop subscribes. Emit is a no-op
# with zero subscribers (zero product behavior change).
_default_bus = AuditBus()


def get_default_audit_bus() -> AuditBus:
    return _default_bus


async def emit_audit(
    bus: Optional[AuditBus],
    *,
    layer: AuditLayer,
    phase: AuditPhase,
    name: str,
    payload: Optional[Dict[str, Any]] = None,
    agent_run_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
) -> None:
    """Emit on ``bus`` or the process default. Always awaited by callers."""
    target = bus if bus is not None else _default_bus
    await target.emit(
        AuditEvent(
            layer=layer,
            phase=phase,
            name=name,
            payload=dict(payload or {}),
            agent_run_id=agent_run_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
        )
    )
