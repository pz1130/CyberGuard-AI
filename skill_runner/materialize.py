"""Write a skill bundle into a throwaway directory, safely.

Standalone by design: this package must not import from ``app`` (mirroring the
rule ``tool_runner`` already follows), so the path rules are restated here
rather than shared with the importer.
"""
from __future__ import annotations

import base64
import os
import re
import stat
from typing import Any, Dict, List, Tuple


class MaterializeError(Exception):
    """A bundle payload violated a path or size rule."""


def safe_relative_path(name: str) -> str:
    """Normalize a bundle path, refusing anything that escapes the root."""
    normalized = (name or "").replace("\\", "/")
    if not normalized:
        raise MaterializeError("empty path in bundle")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise MaterializeError(f"absolute path in bundle: {name}")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise MaterializeError(f"path traversal in bundle: {name}")
    if not parts:
        raise MaterializeError(f"empty path in bundle: {name}")
    return "/".join(parts)


def materialize(files: List[Dict[str, Any]], root: str) -> Tuple[str, str]:
    """Write ``files`` under ``root/bundle`` and create ``root/scratch``.

    Returns ``(bundle_dir, scratch_dir)``. The bundle tree is left read-only;
    the scratch dir is the only place the script may write.
    """
    bundle = os.path.join(root, "bundle")
    scratch = os.path.join(root, "scratch")
    os.makedirs(bundle, exist_ok=True)
    os.makedirs(scratch, exist_ok=True)

    written: List[str] = []
    for entry in files or []:
        rel = safe_relative_path(entry.get("path", ""))
        target = os.path.join(bundle, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            payload = base64.b64decode(entry.get("content_b64") or "", validate=True)
        except Exception as e:
            raise MaterializeError(f"undecodable content for {rel}: {e}") from e
        with open(target, "wb") as fh:
            fh.write(payload)
        written.append(target)

    # Read + execute only. Directories keep +x so they stay traversable.
    for path in written:
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
    for dirpath, dirnames, _ in os.walk(bundle):
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), stat.S_IRUSR | stat.S_IXUSR)
    os.chmod(bundle, stat.S_IRUSR | stat.S_IXUSR)
    os.chmod(scratch, stat.S_IRWXU)
    return bundle, scratch


def unlock_for_removal(root: str) -> None:
    """Restore write permission on every directory under ``root``.

    Unlinking a file needs write permission on its *directory*, not on the file,
    so the read-only tree ``materialize`` leaves behind cannot be deleted until
    the directories are writable again.
    """
    for dirpath, dirnames, _ in os.walk(root):
        for d in dirnames:
            try:
                os.chmod(os.path.join(dirpath, d), stat.S_IRWXU)
            except OSError:
                pass
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
