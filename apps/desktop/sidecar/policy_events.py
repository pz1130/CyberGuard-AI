"""Policy events log (M4 privilege escalation trail).

Separate from the audit hash chain payload detail: structured policy decisions
that explain why a sandbox denial was overridden after approval.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.paths import audit_dir

logger = logging.getLogger("cyberguard.desktop.policy_events")


def policy_events_path() -> Path:
    return audit_dir() / "policy_events.jsonl"


def append_policy_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    approval_type: str = "self",
) -> Dict[str, Any]:
    """Append one policy event (best-effort). Also mirrors to audit chain."""
    entry = {
        "event_id": str(uuid.uuid4()),
        "ts": time.time(),
        "event_type": str(event_type),
        "run_id": run_id,
        "session_id": session_id,
        "plan_id": plan_id,
        "approval_type": approval_type if approval_type in ("self", "segregation", "none") else "self",
        "payload": payload or {},
    }
    try:
        path = policy_events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("policy_event write failed: %s", type(exc).__name__)

    try:
        from apps.desktop.sidecar.audit_chain import append_event

        append_event(
            "policy_event",
            {
                "policy_event_type": event_type,
                "plan_id": plan_id,
                **(payload or {}),
            },
            approval_type=entry["approval_type"],
            session_id=session_id,
            run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        logger.debug("policy_event audit mirror failed", exc_info=True)

    return entry


def tail_policy_events(n: int = 50) -> List[Dict[str, Any]]:
    path = policy_events_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-max(1, n) :]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
