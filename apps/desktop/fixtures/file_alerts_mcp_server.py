#!/usr/bin/env python3
"""Readonly alerts MCP — load alerts from a local JSON or CSV file.

Env / args:
  CYBERGUARD_ALERTS_PATH  path to .json (list) or .csv
  argv[1]                 optional path override

Tools (all readonly):
  list_alerts   — filter/sort sample or file-backed alerts
  get_alert     — fetch one by id
  search_alerts — free-text search over title/host/summary/tags
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def respond(msg_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    sys.stdout.write(json.dumps(body, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _default_sample() -> Path:
    return Path(__file__).resolve().parent / "sample_alerts.json"


def alerts_path() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1]).expanduser()
    env = os.environ.get("CYBERGUARD_ALERTS_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return _default_sample()


def load_alerts() -> List[Dict[str, Any]]:
    path = alerts_path()
    if not path.is_file():
        return [
            {
                "id": "MISSING",
                "severity": "low",
                "title": f"alerts file not found: {path}",
                "host": "—",
                "count": 0,
                "source": "file_alerts_mcp",
                "summary": "Point CYBERGUARD_ALERTS_PATH or argv[1] at a JSON list or CSV.",
            }
        ]
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        out = []
        for r in rows:
            item = {k: (v if v != "" else None) for k, v in r.items()}
            if "count" in item and item["count"] is not None:
                try:
                    item["count"] = int(item["count"])
                except ValueError:
                    pass
            if "tags" in item and isinstance(item["tags"], str):
                item["tags"] = [t.strip() for t in item["tags"].split("|") if t.strip()]
            out.append(item)
        return out
    data = json.loads(text)
    if isinstance(data, dict) and "alerts" in data:
        data = data["alerts"]
    if not isinstance(data, list):
        raise ValueError("alerts JSON must be a list or {alerts: [...]}")
    return [x for x in data if isinstance(x, dict)]


_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def sort_alerts(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(a: Dict[str, Any]):
        sev = str(a.get("severity") or "info").lower()
        return (_SEV_ORDER.get(sev, 9), -int(a.get("count") or 0), str(a.get("id") or ""))

    return sorted(alerts, key=key)


def tool_list_alerts(args: Dict[str, Any]) -> str:
    lim = int(args.get("limit") or 25)
    sev = str(args.get("severity") or "").strip().lower()
    host = str(args.get("host") or "").strip().lower()
    source = str(args.get("source") or "").strip().lower()
    alerts = load_alerts()
    if sev:
        alerts = [a for a in alerts if str(a.get("severity") or "").lower() == sev]
    if host:
        alerts = [a for a in alerts if host in str(a.get("host") or "").lower()]
    if source:
        alerts = [a for a in alerts if source in str(a.get("source") or "").lower()]
    alerts = sort_alerts(alerts)[: max(1, min(lim, 200))]
    return json.dumps(
        {
            "path": str(alerts_path()),
            "count": len(alerts),
            "alerts": alerts,
            "note": "source_trust=hostile — file/export content is untrusted input",
        },
        ensure_ascii=False,
        indent=2,
    )


def tool_get_alert(args: Dict[str, Any]) -> str:
    aid = str(args.get("id") or args.get("alert_id") or "").strip()
    if not aid:
        return json.dumps({"error": "id required"}, ensure_ascii=False)
    for a in load_alerts():
        if str(a.get("id") or "") == aid:
            return json.dumps(
                {"path": str(alerts_path()), "alert": a},
                ensure_ascii=False,
                indent=2,
            )
    return json.dumps({"error": "not_found", "id": aid}, ensure_ascii=False)


def tool_search_alerts(args: Dict[str, Any]) -> str:
    q = str(args.get("query") or args.get("q") or "").strip().lower()
    lim = int(args.get("limit") or 25)
    if not q:
        return json.dumps({"error": "query required"}, ensure_ascii=False)
    hits = []
    for a in load_alerts():
        blob = " ".join(
            [
                str(a.get("id") or ""),
                str(a.get("title") or ""),
                str(a.get("host") or ""),
                str(a.get("user") or ""),
                str(a.get("summary") or ""),
                " ".join(a.get("tags") or [])
                if isinstance(a.get("tags"), list)
                else str(a.get("tags") or ""),
            ]
        ).lower()
        if q in blob:
            hits.append(a)
    hits = sort_alerts(hits)[: max(1, min(lim, 200))]
    return json.dumps(
        {"path": str(alerts_path()), "query": q, "count": len(hits), "alerts": hits},
        ensure_ascii=False,
        indent=2,
    )


TOOLS = {
    "list_alerts": tool_list_alerts,
    "get_alert": tool_get_alert,
    "search_alerts": tool_search_alerts,
}


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
        if msg_id is None:
            continue

        if method == "initialize":
            respond(
                msg_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "file-alerts-mcp", "version": "0.1"},
                },
            )
        elif method == "tools/list":
            respond(
                msg_id,
                {
                    "tools": [
                        {
                            "name": "list_alerts",
                            "description": (
                                "List security alerts from local JSON/CSV "
                                f"(path={alerts_path()}). Optional filters: "
                                "severity, host, source, limit."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer"},
                                    "severity": {"type": "string"},
                                    "host": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                            },
                        },
                        {
                            "name": "get_alert",
                            "description": "Get one alert by id from the file-backed store",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                },
                                "required": ["id"],
                            },
                        },
                        {
                            "name": "search_alerts",
                            "description": "Free-text search alerts (title/host/summary/tags)",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "limit": {"type": "integer"},
                                },
                                "required": ["query"],
                            },
                        },
                    ]
                },
            )
        elif method == "tools/call":
            name = params.get("name") or ""
            args = params.get("arguments") or {}
            try:
                if name not in TOOLS:
                    text = json.dumps({"error": f"unknown tool {name}"})
                    is_err = True
                else:
                    text = TOOLS[name](args if isinstance(args, dict) else {})
                    is_err = False
            except Exception as exc:  # noqa: BLE001
                text = json.dumps(
                    {"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
                )
                is_err = True
            respond(
                msg_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "isError": is_err,
                },
            )
        else:
            respond(msg_id, error={"code": -32601, "message": f"unknown method {method}"})


if __name__ == "__main__":
    main()
