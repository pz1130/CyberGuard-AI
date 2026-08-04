"""Structured tool results — ``is_error`` is explicit, not string sniffing (INV-32)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# Prefixes that *are* control-plane notices produced by the loop itself.
# Real tool payloads that happen to contain "ERROR" must not flip is_error.
_CONTROL_PREFIXES = (
    "LOOP_DETECTED:",
    "BUDGET_EXHAUSTED:",
    "NEEDS_APPROVAL:",
)


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    status: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def for_model(self) -> str:
        """String form re-injected into the LLM tool message."""
        return self.content


def normalize_tool_result(result: Any) -> ToolResult:
    """Normalize heterogeneous executor returns into ``ToolResult``.

    * ``ToolResult`` — returned as-is
    * ``dict`` with ``status`` / ``is_error`` / stdout|error — structured path
    * plain str — **is_error defaults False** unless it is a known control-plane
      notice prefix. Content containing the substring ``ERROR`` alone does **not**
      set is_error (INV-32).
    """
    if isinstance(result, ToolResult):
        return result

    if isinstance(result, dict):
        status = result.get("status")
        if "is_error" in result:
            is_error = bool(result["is_error"])
        else:
            is_error = status in (
                "error",
                "denied",
                "halted",
                "failed",
            )
            # needs_approval is a control outcome, surface as error to the model loop
            if status == "needs_approval":
                is_error = True
        if result.get("stdout") is not None and status == "completed":
            content = str(result.get("stdout") or "") or "(no output)"
        elif result.get("error") is not None:
            content = str(result["error"])
        elif result.get("content") is not None:
            content = str(result["content"])
        else:
            try:
                content = json.dumps(result, ensure_ascii=False, default=str)
            except TypeError:
                content = str(result)
        return ToolResult(
            content=content,
            is_error=is_error,
            status=str(status) if status is not None else None,
            meta={k: v for k, v in result.items() if k not in ("stdout", "error", "content")},
        )

    text = "" if result is None else str(result)
    is_error = text.startswith(_CONTROL_PREFIXES)
    # Legacy dispatch strings: "ERROR: ..." from our own wrappers
    if text.startswith("ERROR:"):
        is_error = True
    return ToolResult(content=text, is_error=is_error)
