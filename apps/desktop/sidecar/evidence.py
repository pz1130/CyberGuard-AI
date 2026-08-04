"""Evidence browser store (M5): sha256 + read-only registration.

Evidence is never loaded into system prompt. Catalog is for analyst UI and
hash integrity display. Files may live outside data_root (user-chosen paths);
we only store metadata + hash, and open read-only for re-hash verification.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.evidence")

CHUNK = 1024 * 1024


def evidence_dir() -> Path:
    p = data_root() / "evidence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def evidence_index_path() -> Path:
    return evidence_dir() / "index.jsonl"


def sha256_file(path: Path, *, max_bytes: Optional[int] = None) -> str:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if max_bytes is not None and total >= max_bytes:
                break
    return h.hexdigest()


@dataclass
class EvidenceItem:
    evidence_id: str
    path: str
    name: str
    sha256: str
    size: int
    readonly: bool
    trusted_dir: bool
    registered_at: float
    note: str = ""
    source: str = "user"

    def public_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "path": self.path,
            "name": self.name,
            "sha256": self.sha256,
            "size": self.size,
            "readonly": self.readonly,
            "trusted_dir": self.trusted_dir,
            "registered_at": self.registered_at,
            "note": self.note,
            "source": self.source,
            # UI: never claim write access
            "mount": "read-only",
        }


class EvidenceStore:
    def __init__(self, index_path: Optional[Path] = None) -> None:
        self.index_path = index_path or evidence_index_path()
        evidence_dir()

    def _append(self, item: EvidenceItem) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item.public_dict(), ensure_ascii=False) + "\n")

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.index_path.is_file():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            return []
        return rows[-limit:]

    def register(
        self,
        path: str,
        *,
        note: str = "",
        source: str = "user",
    ) -> Dict[str, Any]:
        p = Path(path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"not a file: {path}")
        # Read-only open for hashing
        digest = sha256_file(p)
        size = p.stat().st_size
        trusted = False
        try:
            from apps.desktop.sidecar.trust_gate import get_trust_gate

            trusted = get_trust_gate().allow_load(p.parent, purpose="evidence_dir")
        except Exception:  # noqa: BLE001
            trusted = False

        item = EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            path=str(p.resolve()),
            name=p.name,
            sha256=digest,
            size=int(size),
            readonly=True,
            trusted_dir=trusted,
            registered_at=time.time(),
            note=note or "",
            source=source,
        )
        self._append(item)
        try:
            from apps.desktop.sidecar.audit_chain import append_event

            append_event(
                "evidence_register",
                {
                    "evidence_id": item.evidence_id,
                    "name": item.name,
                    "sha256": item.sha256,
                    "size": item.size,
                    "readonly": True,
                },
                approval_type="self",
            )
        except Exception:  # noqa: BLE001
            pass
        return item.public_dict()

    def verify(self, evidence_id: str) -> Dict[str, Any]:
        for row in self.list(limit=10_000):
            if row.get("evidence_id") == evidence_id:
                path = Path(str(row.get("path") or ""))
                if not path.is_file():
                    return {
                        "ok": False,
                        "evidence_id": evidence_id,
                        "error": "file_missing",
                        "expected_sha256": row.get("sha256"),
                    }
                current = sha256_file(path)
                match = current == row.get("sha256")
                return {
                    "ok": match,
                    "evidence_id": evidence_id,
                    "expected_sha256": row.get("sha256"),
                    "current_sha256": current,
                    "readonly": True,
                    "path": str(path),
                    "name": row.get("name"),
                }
        return {"ok": False, "evidence_id": evidence_id, "error": "unknown_id"}


_STORE: Optional[EvidenceStore] = None


def get_evidence_store() -> EvidenceStore:
    global _STORE
    if _STORE is None:
        _STORE = EvidenceStore()
    return _STORE


def reset_evidence_store_for_tests() -> None:
    global _STORE
    _STORE = None
