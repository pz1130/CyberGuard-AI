"""Project Trust Gate (M5 / INV-14).

Sandbox controls what tools *can do*. Trust Gate controls whether to *load*
local files (skills, context, prompts) from a directory into the agent.

Defaults:
  - Builtin package skills: always trusted (global)
  - App-managed ``skills/approved``: trusted (user-approved path)
  - App-managed ``skills/drafts``: never loaded (INV-20)
  - Any other path (workspace, external project dirs): **default untrusted**
    until explicit trust decision in trust.json

Failure to evaluate trust is a hard deny (INV-25 — no silent pass).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.trust_gate")

TrustLevel = Literal["trusted", "untrusted", "ask"]
Decision = Literal["allow", "deny", "ask"]


def trust_store_path() -> Path:
    return data_root() / "trust.json"


def _normalize_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path.expanduser())


@dataclass
class TrustDecision:
    path: str
    level: TrustLevel
    decision: Decision
    reason: str
    source: str = "rule"  # rule | store | builtin


class TrustGate:
    """Load/save trust.json and evaluate paths."""

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self.store_path = store_path or trust_store_path()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.store_path.is_file():
            return {"version": 1, "paths": {}, "updated_at": None}
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("trust.json root must be object")
            raw.setdefault("version", 1)
            raw.setdefault("paths", {})
            if not isinstance(raw["paths"], dict):
                raise ValueError("paths must be object")
            return raw
        except Exception as exc:  # noqa: BLE001
            # INV-25: trust load failure is hard — treat as empty deny-all for
            # project paths; log loudly. Do not invent trust.
            logger.error("trust.json load failed: %s — denying project loads", type(exc).__name__)
            return {
                "version": 1,
                "paths": {},
                "updated_at": None,
                "load_error": type(exc).__name__,
            }

    def save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = time.time()
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.store_path)
        try:
            os.chmod(self.store_path, 0o600)
        except OSError:
            pass

    def set_trust(self, path: str | Path, level: TrustLevel, *, note: str = "") -> Dict[str, Any]:
        if level not in ("trusted", "untrusted", "ask"):
            raise ValueError("level must be trusted|untrusted|ask")
        key = _normalize_key(Path(path))
        self._data.setdefault("paths", {})[key] = {
            "level": level,
            "note": note,
            "updated_at": time.time(),
        }
        self.save()
        return {"path": key, "level": level, "note": note}

    def revoke(self, path: str | Path) -> bool:
        key = _normalize_key(Path(path))
        paths = self._data.get("paths") or {}
        if key not in paths:
            return False
        del paths[key]
        self.save()
        return True

    def list_decisions(self) -> List[Dict[str, Any]]:
        out = []
        for k, v in sorted((self._data.get("paths") or {}).items()):
            if isinstance(v, dict):
                out.append({"path": k, **v})
        return out

    def is_global_resource(self, path: Path) -> bool:
        """Package builtin skills and app-managed approved skills are global."""
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return False
        # Builtin package skills
        try:
            from apps.desktop.sidecar.skill_loader import builtin_dir, approved_dir

            for root in (builtin_dir(), approved_dir()):
                try:
                    resolved.relative_to(root.resolve())
                    return True
                except ValueError:
                    continue
        except Exception:  # noqa: BLE001
            pass
        return False

    def evaluate(self, path: str | Path, *, purpose: str = "load") -> TrustDecision:
        """Return allow/deny/ask for loading resources from path."""
        p = Path(path)
        try:
            key = _normalize_key(p)
            resolved = Path(key)
        except Exception as exc:  # noqa: BLE001
            return TrustDecision(
                path=str(path),
                level="untrusted",
                decision="deny",
                reason=f"path resolve failed: {type(exc).__name__}",
                source="error",
            )

        if self.is_global_resource(resolved if resolved.is_file() else resolved):
            return TrustDecision(
                path=key,
                level="trusted",
                decision="allow",
                reason="global/builtin or app-approved skill path",
                source="builtin",
            )

        # Check exact path and parents
        paths: Dict[str, Any] = self._data.get("paths") or {}
        candidates = [resolved]
        if resolved.is_file():
            candidates.append(resolved.parent)
        # Walk up a few levels for project root trust
        cur = resolved if resolved.is_dir() else resolved.parent
        for _ in range(8):
            candidates.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent

        for cand in candidates:
            ck = _normalize_key(cand)
            entry = paths.get(ck)
            if not entry or not isinstance(entry, dict):
                continue
            level = str(entry.get("level") or "ask")
            if level == "trusted":
                return TrustDecision(
                    path=key,
                    level="trusted",
                    decision="allow",
                    reason=f"trusted via {ck}",
                    source="store",
                )
            if level == "untrusted":
                return TrustDecision(
                    path=key,
                    level="untrusted",
                    decision="deny",
                    reason=f"explicitly untrusted via {ck}",
                    source="store",
                )
            if level == "ask":
                return TrustDecision(
                    path=key,
                    level="ask",
                    decision="ask",
                    reason=f"ask configured for {ck}",
                    source="store",
                )

        # Default: project-local resources denied until trusted (INV-14)
        return TrustDecision(
            path=key,
            level="untrusted",
            decision="deny",
            reason=(
                f"default deny for project-local {purpose} (INV-14); "
                "call trust.set with level=trusted after review"
            ),
            source="rule",
        )

    def allow_load(self, path: str | Path, *, purpose: str = "load") -> bool:
        d = self.evaluate(path, purpose=purpose)
        return d.decision == "allow"

    def public_status(self) -> Dict[str, Any]:
        return {
            "store": str(self.store_path),
            "decisions": len(self._data.get("paths") or {}),
            "load_error": self._data.get("load_error"),
            "default": "deny_project_local",
        }


_GATE: Optional[TrustGate] = None


def get_trust_gate() -> TrustGate:
    global _GATE
    if _GATE is None:
        _GATE = TrustGate()
    return _GATE


def reset_trust_gate_for_tests() -> None:
    global _GATE
    _GATE = None
