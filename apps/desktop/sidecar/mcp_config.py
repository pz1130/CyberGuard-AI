"""Load MCP server definitions for the desktop sidecar.

File: ``{data_root}/mcp_servers.json``

Example::

  {
    "servers": [
      {
        "id": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/readonly-data"],
        "readonly": true,
        "enabled": true,
        "timeout_seconds": 30,
        "description": "Read-only files under a data folder"
      }
    ]
  }

Env override (optional, single server for quick demos)::

  CYBERGUARD_MCP_COMMAND=/usr/bin/npx
  CYBERGUARD_MCP_ARGS=-y,@modelcontextprotocol/server-filesystem,/tmp/data
  CYBERGUARD_MCP_ID=demo
"""
from __future__ import annotations

import json
import logging
import os
from typing import List

from apps.desktop.sidecar.mcp_stdio import McpServerConfig
from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.mcp_config")


def load_mcp_servers() -> List[McpServerConfig]:
    servers: List[McpServerConfig] = []

    # Env single-server shortcut
    cmd = os.environ.get("CYBERGUARD_MCP_COMMAND", "").strip()
    if cmd:
        args_raw = os.environ.get("CYBERGUARD_MCP_ARGS", "")
        args = [a for a in args_raw.split(",") if a != ""] if args_raw else []
        servers.append(
            McpServerConfig(
                id=os.environ.get("CYBERGUARD_MCP_ID", "env-mcp"),
                command=cmd,
                args=args,
                readonly=os.environ.get("CYBERGUARD_MCP_READONLY", "true").lower()
                != "false",
                enabled=True,
                description="From CYBERGUARD_MCP_* env",
            )
        )

    path = data_root() / "mcp_servers.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data.get("servers") or []:
                if not isinstance(entry, dict):
                    continue
                cfg = McpServerConfig.from_dict(entry)
                if cfg.enabled and cfg.command:
                    # avoid duplicate ids from env
                    if any(s.id == cfg.id for s in servers):
                        continue
                    servers.append(cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_servers.json read failed: %s", type(exc).__name__)

    return servers
