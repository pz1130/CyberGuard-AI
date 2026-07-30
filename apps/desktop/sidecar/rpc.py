"""Minimal JSONL request/response codec."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, TextIO


def read_request(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    data = json.loads(line)
    if not isinstance(data, dict) or "method" not in data:
        raise ValueError("invalid request: need method")
    return data


def write_message(fp: TextIO, payload: Dict[str, Any]) -> None:
    fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    fp.flush()


def result_msg(req_id: Any, result: Any) -> Dict[str, Any]:
    return {"id": req_id, "result": result}


def event_msg(req_id: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": req_id, "event": event}


def error_msg(req_id: Any, code: str, message: str) -> Dict[str, Any]:
    return {"id": req_id, "error": {"code": code, "message": message}}
