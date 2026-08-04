"""Run pause / resume for provider or MCP disconnect (M5).

Standalone: disconnect is LLM Provider or MCP endpoint, not a server.
On recoverable network failure we mark the run paused, persist a checkpoint
under sessions/, and allow resume from the same messages state.

Not a full durable agent VM — checkpoint is messages + task + tier metadata.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.paths import sessions_dir

logger = logging.getLogger("cyberguard.desktop.run_pause")

PAUSE_REASON_PROVIDER = "provider_unavailable"
PAUSE_REASON_MCP = "mcp_unavailable"
PAUSE_REASON_USER = "user_pause"


def checkpoints_dir() -> Path:
    p = sessions_dir() / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p


def checkpoint_path(run_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)
    return checkpoints_dir() / f"{safe}.json"


def is_networkish_error(exc: BaseException | str) -> bool:
    text = str(exc).lower()
    needles = (
        "connection",
        "timeout",
        "timed out",
        "network",
        "temporarily unavailable",
        "name or service not known",
        "nodename nor servname",
        "connection reset",
        "connection refused",
        "ssl",
        "unreachable",
        "apiconnectionerror",
        "connecterror",
        "readtimeout",
        "connecttimeout",
    )
    return any(n in text for n in needles)


def save_checkpoint(
    *,
    run_id: str,
    task: str,
    tier: str,
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    reason: str = PAUSE_REASON_PROVIDER,
    session_id: Optional[str] = None,
    tool_call_log: Optional[List[Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "checkpoint_id": str(uuid.uuid4()),
        "run_id": run_id,
        "task": task,
        "tier": tier,
        "session_id": session_id,
        "system_prompt": system_prompt,
        "messages": messages,
        "tool_call_log": tool_call_log or [],
        "reason": reason,
        "status": "paused",
        "paused_at": time.time(),
        "extra": extra or {},
    }
    path = checkpoint_path(run_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    try:
        from apps.desktop.sidecar.audit_chain import append_event

        append_event(
            "run_paused",
            {"run_id": run_id, "reason": reason, "messages": len(messages)},
            approval_type="self",
            session_id=session_id,
            run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        pass
    return payload


def load_checkpoint(run_id: str) -> Optional[Dict[str, Any]]:
    path = checkpoint_path(run_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        logger.warning("checkpoint load failed for %s", run_id)
        return None


def list_paused(limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    d = checkpoints_dir()
    for path in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("status") == "paused":
                out.append(
                    {
                        "run_id": data.get("run_id"),
                        "task": (data.get("task") or "")[:200],
                        "tier": data.get("tier"),
                        "reason": data.get("reason"),
                        "paused_at": data.get("paused_at"),
                        "message_count": len(data.get("messages") or []),
                    }
                )
        except Exception:  # noqa: BLE001
            continue
        if len(out) >= limit:
            break
    return out


def clear_checkpoint(run_id: str) -> bool:
    path = checkpoint_path(run_id)
    if path.is_file():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


def mark_resumed(run_id: str) -> None:
    try:
        from apps.desktop.sidecar.audit_chain import append_event

        append_event(
            "run_resumed",
            {"run_id": run_id},
            approval_type="self",
            run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        pass
    clear_checkpoint(run_id)
