"""Local append-only audit hash chain (M3).

Tamper-evident JSONL under managed audit/. Not WORM — do not claim durability
or legal hold equivalence (INV-38).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.paths import audit_dir

GENESIS = "0" * 64
_LOCK = threading.Lock()


def chain_path() -> Path:
    return audit_dir() / "chain.jsonl"


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _hash_entry(prev_hash: str, body: Dict[str, Any]) -> str:
    material = prev_hash + "|" + _canonical(body)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _tail_hash(path: Path) -> tuple[int, str]:
    """Return (last_seq, last_entry_hash)."""
    if not path.is_file() or path.stat().st_size == 0:
        return 0, GENESIS
    last_line = ""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        # read last ~8KB
        f.seek(max(0, size - 8192))
        chunk = f.read().decode("utf-8", errors="replace")
    for line in chunk.splitlines():
        if line.strip():
            last_line = line
    if not last_line:
        return 0, GENESIS
    try:
        obj = json.loads(last_line)
        return int(obj.get("seq") or 0), str(obj.get("entry_hash") or GENESIS)
    except Exception:
        return 0, GENESIS


def append_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    approval_type: str = "self",
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one audit entry. approval_type defaults to self (standalone)."""
    if approval_type not in ("self", "segregation", "none"):
        approval_type = "self"
    body = {
        "event_type": str(event_type),
        "ts": time.time(),
        "event_id": str(uuid.uuid4()),
        "approval_type": approval_type,
        "session_id": session_id,
        "run_id": run_id,
        "payload": payload or {},
    }
    # Never store raw secrets if caller slips
    for k in list((body.get("payload") or {}).keys()):
        lk = str(k).lower()
        if any(x in lk for x in ("api_key", "password", "secret", "token", "authorization")):
            body["payload"][k] = "[redacted]"

    path = chain_path()
    with _LOCK:
        seq, prev = _tail_hash(path)
        entry = {
            "seq": seq + 1,
            "prev_hash": prev,
            **body,
        }
        entry["entry_hash"] = _hash_entry(prev, {k: v for k, v in entry.items() if k != "entry_hash"})
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            f.flush()
    return {
        "seq": entry["seq"],
        "entry_hash": entry["entry_hash"],
        "prev_hash": entry["prev_hash"],
        "event_type": entry["event_type"],
        "approval_type": entry["approval_type"],
    }


def verify_chain(path: Optional[Path] = None) -> Dict[str, Any]:
    """Verify full chain integrity. Returns ok/broken_at/count."""
    p = path or chain_path()
    if not p.is_file():
        return {"ok": True, "count": 0, "broken_at": None, "message": "empty"}
    prev = GENESIS
    count = 0
    with p.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "count": count,
                    "broken_at": line_no,
                    "message": "invalid_json",
                }
            count += 1
            if str(obj.get("prev_hash")) != prev:
                return {
                    "ok": False,
                    "count": count,
                    "broken_at": line_no,
                    "message": "prev_hash_mismatch",
                }
            body = {k: v for k, v in obj.items() if k != "entry_hash"}
            expected = _hash_entry(prev, body)
            if str(obj.get("entry_hash")) != expected:
                return {
                    "ok": False,
                    "count": count,
                    "broken_at": line_no,
                    "message": "entry_hash_mismatch",
                }
            if int(obj.get("seq") or 0) != count:
                return {
                    "ok": False,
                    "count": count,
                    "broken_at": line_no,
                    "message": "seq_gap",
                }
            prev = str(obj["entry_hash"])
    return {"ok": True, "count": count, "broken_at": None, "message": "ok"}


def tail(n: int = 20) -> List[Dict[str, Any]]:
    p = chain_path()
    if not p.is_file():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-max(1, n) :]:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
