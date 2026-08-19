"""Local UI preferences (theme, font size) — not secrets."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.ui_prefs")

ALLOWED_THEMES = frozenset({"dark", "light", "system"})
ALLOWED_FONT = frozenset({"small", "medium", "large"})
ALLOWED_LANGUAGE = frozenset({"zh", "en", "system"})
DEFAULTS: Dict[str, Any] = {"theme": "dark", "font_size": "medium", "language": "system"}


def _path() -> Path:
    return data_root() / "ui_prefs.json"


def get_prefs() -> Dict[str, Any]:
    path = _path()
    data: Dict[str, Any] = dict(DEFAULTS)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({k: v for k, v in raw.items() if k in DEFAULTS or k in ("theme", "font_size", "language")})
        except Exception as exc:  # noqa: BLE001
            logger.warning("ui_prefs read failed: %s", type(exc).__name__)
    theme = str(data.get("theme") or "dark")
    if theme not in ALLOWED_THEMES:
        theme = "dark"
    font = str(data.get("font_size") or "medium")
    if font not in ALLOWED_FONT:
        font = "medium"
    language = str(data.get("language") or "system")
    if language not in ALLOWED_LANGUAGE:
        language = "system"
    return {"theme": theme, "font_size": font, "language": language}


def set_prefs(partial: Dict[str, Any]) -> Dict[str, Any]:
    current = get_prefs()
    if "theme" in partial and partial["theme"] is not None:
        theme = str(partial["theme"]).strip().lower()
        if theme in ALLOWED_THEMES:
            current["theme"] = theme
    if "font_size" in partial and partial["font_size"] is not None:
        font = str(partial["font_size"]).strip().lower()
        if font in ALLOWED_FONT:
            current["font_size"] = font
    if "language" in partial and partial["language"] is not None:
        language = str(partial["language"]).strip().lower()
        if language in ALLOWED_LANGUAGE:
            current["language"] = language
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return {"ok": True, "prefs": current}
