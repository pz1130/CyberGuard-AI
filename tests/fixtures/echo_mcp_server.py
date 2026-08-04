#!/usr/bin/env python3
"""Minimal STDIO MCP server for tests (JSON-RPC line protocol).

Tools:
  - echo: returns arguments as text
  - list_alerts: returns a tiny fake alert list (golden-path demo)
  - secret_probe: reports whether CYBERGUARD_MCP_SECRET (or custom) is set
"""
from __future__ import annotations

import json
import os
import sys


def respond(msg_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    sys.stdout.write(json.dumps(body) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        msg_id = req.get("id")
        params = req.get("params") or {}

        # notifications have no id
        if msg_id is None:
            continue

        if method == "initialize":
            respond(
                msg_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "echo-mcp", "version": "0.1"},
                },
            )
        elif method == "tools/list":
            respond(
                msg_id,
                {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo arguments as JSON text",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string"},
                                },
                            },
                        },
                        {
                            "name": "list_alerts",
                            "description": "Return sample security alerts for triage demos",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer"},
                                },
                            },
                        },
                        {
                            "name": "secret_probe",
                            "description": "Test helper: whether injected MCP secret env is present",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "env_name": {"type": "string"},
                                },
                            },
                        },
                    ]
                },
            )
        elif method == "tools/call":
            name = (params.get("name") or "")
            args = params.get("arguments") or {}
            if name == "echo":
                text = json.dumps(args, ensure_ascii=False)
            elif name == "list_alerts":
                alerts = [
                    {
                        "id": "A-1001",
                        "severity": "high",
                        "title": "Suspicious PowerShell from workstation",
                        "host": "ws-042",
                        "count": 12,
                    },
                    {
                        "id": "A-1002",
                        "severity": "medium",
                        "title": "Failed SSH bursts",
                        "host": "jump-01",
                        "count": 84,
                    },
                    {
                        "id": "A-1003",
                        "severity": "low",
                        "title": "AV signature update lag",
                        "host": "ws-017",
                        "count": 1,
                    },
                ]
                lim = int(args.get("limit") or 10)
                text = json.dumps(alerts[:lim], ensure_ascii=False, indent=2)
            elif name == "secret_probe":
                env_name = str(args.get("env_name") or "CYBERGUARD_MCP_SECRET")
                val = os.environ.get(env_name) or ""
                text = json.dumps(
                    {
                        "env_name": env_name,
                        "has_secret": bool(val),
                        # suffix only for tests — never full secret
                        "suffix": val[-4:] if len(val) >= 4 else "",
                        "length": len(val),
                    },
                    ensure_ascii=False,
                )
            else:
                respond(
                    msg_id,
                    error={"code": -32601, "message": f"unknown tool {name}"},
                )
                continue
            respond(
                msg_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            )
        else:
            respond(
                msg_id,
                error={"code": -32601, "message": f"unknown method {method}"},
            )


if __name__ == "__main__":
    main()
