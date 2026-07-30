"""Runtime tool-argument validation against JSON-schema-like input_schema (INV-30).

Minimal subset used by CyberGuard tool pool / MCP tools:
  type, properties, required, enum, integer/number/string/boolean/object/array.

Does not pull in jsonschema — keep agent_core dependency-light.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


class SchemaValidationError(ValueError):
    """Arguments failed schema validation; must not reach execute (INV-30)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        # bool is a subclass of int — reject
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return True
        return False
    if expected == "number":
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True  # unknown type — do not over-reject


def validate_tool_arguments(
    args: Mapping[str, Any],
    input_schema: Optional[Mapping[str, Any]],
    *,
    allow_extra: bool = False,
) -> Dict[str, Any]:
    """Validate ``args`` against ``input_schema``; return a plain dict copy.

    Raises ``SchemaValidationError`` on failure. Empty/missing schema → passthrough
    (tools without a declared schema are not blocked here).
    """
    out = dict(args)
    if not input_schema:
        return out

    props = input_schema.get("properties") or {}
    required: List[str] = list(input_schema.get("required") or [])

    if not allow_extra:
        for k in out:
            if props and k not in props:
                raise SchemaValidationError(f"unknown argument: {k!r}")

    for k in required:
        if k not in out:
            raise SchemaValidationError(f"missing required argument: {k!r}")

    for k, v in out.items():
        prop = props.get(k) if props else None
        if not isinstance(prop, Mapping):
            continue
        enum = prop.get("enum")
        if enum is not None and v not in enum:
            raise SchemaValidationError(f"argument {k!r}={v!r} not in enum {enum}")
        t = prop.get("type")
        if t and not _type_ok(v, t):
            raise SchemaValidationError(
                f"argument {k!r} must be a {t}, got {v!r}"
            )

    return out


def schema_from_tool(tool: Any) -> Optional[Dict[str, Any]]:
    """Best-effort extract input_schema from a tool row / dict / metadata."""
    if tool is None:
        return None
    if isinstance(tool, Mapping):
        raw = tool.get("input_schema") or tool.get("input_schema_json")
    else:
        raw = getattr(tool, "input_schema", None)
        if raw is None:
            raw = getattr(tool, "input_schema_json", None)
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None
