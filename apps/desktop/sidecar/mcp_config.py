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
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.mcp_stdio import McpServerConfig
from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.mcp_config")


def _config_path() -> Path:
    return data_root() / "mcp_servers.json"


def _read_raw() -> Dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return {"servers": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"servers": []}
        servers = data.get("servers")
        if not isinstance(servers, list):
            data["servers"] = []
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp_servers.json read failed: %s", type(exc).__name__)
        return {"servers": []}


def _atomic_write(data: Dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _redact_env(env: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in (env or {}).items():
        key = str(k)
        if v is None or v == "":
            out[key] = ""
        else:
            out[key] = "***"
    return out


def list_mcp_config_public() -> Dict[str, Any]:
    """All configured servers (incl. disabled) — secrets redacted."""
    raw = _read_raw()
    servers_out: List[Dict[str, Any]] = []
    try:
        from apps.desktop.sidecar.secrets_store import get_mcp_secret
    except Exception:  # noqa: BLE001
        get_mcp_secret = None  # type: ignore

    for entry in raw.get("servers") or []:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("id") or entry.get("name") or "")
        has_secret = False
        if sid and get_mcp_secret:
            try:
                has_secret = bool(get_mcp_secret(sid))
            except Exception:  # noqa: BLE001
                has_secret = False
        servers_out.append(
            {
                "id": sid,
                "command": str(entry.get("command") or ""),
                "args": [str(a) for a in (entry.get("args") or [])],
                "env": _redact_env(entry.get("env") or {}),
                "env_keys": list((entry.get("env") or {}).keys()),
                "timeout_seconds": int(entry.get("timeout_seconds") or 30),
                "readonly": bool(entry.get("readonly", True)),
                "enabled": bool(entry.get("enabled", True)),
                "description": str(entry.get("description") or ""),
                "secret_env": str(
                    entry.get("secret_env")
                    or entry.get("secretEnv")
                    or "CYBERGUARD_MCP_SECRET"
                ),
                "has_secret": has_secret,
            }
        )
    return {"servers": servers_out}


def upsert_mcp_server(params: Dict[str, Any]) -> Dict[str, Any]:
    sid = str(params.get("id") or params.get("name") or "").strip()
    if not sid:
        raise ValueError("id required")
    command = str(params.get("command") or "").strip()
    if not command:
        raise ValueError("command required")

    secret = params.get("secret")
    if secret is not None and str(secret).strip():
        from apps.desktop.sidecar.secrets_store import set_mcp_secret

        set_mcp_secret(sid, str(secret).strip())

    # Preserve existing env values if client only sent redacted ***
    raw = _read_raw()
    existing: Optional[Dict[str, Any]] = None
    for e in raw.get("servers") or []:
        if isinstance(e, dict) and str(e.get("id") or "") == sid:
            existing = e
            break

    env_in = params.get("env")
    if env_in is None:
        env_out = dict((existing or {}).get("env") or {})
    else:
        env_out = {}
        prev_env = dict((existing or {}).get("env") or {})
        for k, v in (env_in or {}).items():
            key = str(k)
            val = str(v) if v is not None else ""
            if val in ("***", "[redacted]") and key in prev_env:
                env_out[key] = prev_env[key]
            else:
                env_out[key] = val

    entry: Dict[str, Any] = {
        "id": sid,
        "command": command,
        "args": [str(a) for a in (params.get("args") or [])],
        "env": env_out,
        "timeout_seconds": int(
            params.get("timeout_seconds")
            if params.get("timeout_seconds") is not None
            else (existing or {}).get("timeout_seconds")
            or 30
        ),
        "readonly": bool(
            params["readonly"]
            if "readonly" in params
            else (existing or {}).get("readonly", True)
        ),
        "enabled": bool(
            params["enabled"]
            if "enabled" in params
            else (existing or {}).get("enabled", True)
        ),
        "description": str(
            params.get("description")
            if params.get("description") is not None
            else (existing or {}).get("description")
            or ""
        ),
        "secret_env": str(
            params.get("secret_env")
            or params.get("secretEnv")
            or (existing or {}).get("secret_env")
            or "CYBERGUARD_MCP_SECRET"
        ),
    }

    servers: List[Any] = []
    replaced = False
    for e in raw.get("servers") or []:
        if isinstance(e, dict) and str(e.get("id") or "") == sid:
            servers.append(entry)
            replaced = True
        else:
            servers.append(e)
    if not replaced:
        servers.append(entry)
    raw["servers"] = servers
    _atomic_write(raw)
    public = list_mcp_config_public()
    match = next((s for s in public["servers"] if s["id"] == sid), entry)
    return {"ok": True, "server": match}


def delete_mcp_server(server_id: str) -> Dict[str, Any]:
    sid = str(server_id or "").strip()
    if not sid:
        raise ValueError("id required")
    raw = _read_raw()
    before = len(raw.get("servers") or [])
    raw["servers"] = [
        e
        for e in (raw.get("servers") or [])
        if not (isinstance(e, dict) and str(e.get("id") or "") == sid)
    ]
    _atomic_write(raw)
    try:
        from apps.desktop.sidecar.secrets_store import delete_mcp_secret

        delete_mcp_secret(sid)
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "deleted": before - len(raw["servers"]) > 0,
        "id": sid,
    }


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

    path = _config_path()
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
