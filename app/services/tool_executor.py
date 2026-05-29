"""Executable Tool pool — validate args, build an injection-safe argv, and run
it in the isolated tool-runner container. See:
  docs/superpowers/specs/2026-05-29-tool-pool-executable-design.md
"""
import json
import os
import shlex
from typing import Any, Dict, List, Optional

import httpx


TOOL_RUNNER_URL = os.environ.get("TOOL_RUNNER_URL", "http://tool-runner:9000")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
OUTPUT_MAX_CHARS = 8000  # mirror internal_agent.TOOL_RESULT_MAX_CHARS


class ToolArgError(ValueError):
    """Raised when supplied args don't satisfy the tool's input schema/template."""


def build_argv(command_template: str, input_schema: Optional[Dict[str, Any]],
               args: Dict[str, Any]) -> List[str]:
    """Turn a command template + args into a safe argv list.

    Placeholders must be standalone `{name}` tokens whose name is declared in the
    schema's properties; each becomes a single argv element (never shell-parsed),
    making command injection structurally impossible.
    """
    schema = input_schema or {}
    props = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []

    for k in args:
        if k not in props:
            raise ToolArgError(f"unknown argument: {k!r}")
    for k in required:
        if k not in args:
            raise ToolArgError(f"missing required argument: {k!r}")

    if not command_template:
        raise ToolArgError("tool has no command_template")

    argv: List[str] = []
    for tok in shlex.split(command_template):
        if len(tok) >= 2 and tok[0] == "{" and tok[-1] == "}":
            name = tok[1:-1]
            if name not in props:
                raise ToolArgError(f"placeholder {tok} not in schema")
            if name not in args:
                raise ToolArgError(f"unfilled placeholder: {name!r}")
            argv.append(str(args[name]))
        elif "{" in tok or "}" in tok:
            raise ToolArgError(f"placeholder must be a standalone token, got {tok!r}")
        else:
            argv.append(tok)
    return argv
