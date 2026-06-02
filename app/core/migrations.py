"""Alembic startup helper for app/main.py.

Centralises the dev-time auto-migrate-and-recover logic so it can be tested
without subprocess.run against a real DB. Production skips this entirely
(CI/CD runs `alembic upgrade` explicitly); the helper is also safe to call
in production if a future caller wants belt-and-braces behaviour.

Recovery rules (in order):
  1. Try `alembic upgrade head` (single-head projects: the common case).
  2. If that fails with `Multiple head revisions` (introduced when more than
     one migration chain head exists, e.g. PR #11's `002b_create_document_chunks`
     alongside `017_agent_episodes`), discover every head with `alembic heads`
     and run `alembic upgrade <head>` once per head.
  3. If the upgrade fails with `DuplicateTableError` / `already exists`
     (existing-DB case: schema was created outside alembic), stamp `head`.
  4. Any other error: log at warning and return False so the app boots
     anyway (matching the prior behaviour).
"""
from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Cmd:
    alembic_ini: str = "/app/alembic.ini"
    upgrade_head: List[str] = ("alembic", "-c", "/app/alembic.ini", "upgrade", "head")
    stamp_head:   List[str] = ("alembic", "-c", "/app/alembic.ini", "stamp", "head")
    heads:        List[str] = ("alembic", "-c", "/app/alembic.ini", "heads")


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _list_heads() -> List[str]:
    """Run `alembic heads` and return the list of revision ids, one per line.

    Strips the ` (head)` decoration alembic appends so the values can be
    passed straight to `alembic upgrade <rev>`.
    """
    proc = _run(list(_Cmd.heads))
    if proc.returncode != 0:
        logger.warning("alembic heads failed: %s", (proc.stderr or proc.stdout).strip())
        return []
    ids: List[str] = []
    for raw in (proc.stdout or "").splitlines():
        rev = raw.strip()
        if not rev:
            continue
        # Each line is "<rev_id> (head)" — drop the suffix.
        rev = rev.split(" ", 1)[0]
        ids.append(rev)
    return ids


def run_alembic_upgrade_on_startup() -> bool:
    """Best-effort alembic upgrade for the dev startup. Never raises.

    Returns True if a clean apply / stamp succeeded, False if we fell through
    to the "unrecoverable, log and continue" branch.
    """
    # 1. Fast path: single head.
    proc = _run(list(_Cmd.upgrade_head))
    if proc.returncode == 0:
        logger.info("Alembic migrations applied successfully")
        return True

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    combined = f"{stdout}\n{stderr}"

    # 2. Multiple heads → upgrade each.
    if "Multiple head revisions" in combined:
        heads = _list_heads()
        if not heads:
            logger.warning("Alembic upgrade failed (multiple heads, none discovered)")
            return False
        ok = True
        for head in heads:
            up = _run(["alembic", "-c", _Cmd.alembic_ini, "upgrade", head])
            if up.returncode != 0:
                logger.warning("alembic upgrade %s failed: %s", head,
                               (up.stderr or up.stdout).strip())
                ok = False
        if ok:
            logger.info("Applied multiple alembic heads: %s", ", ".join(heads))
        return ok

    # 3. Schema-already-exists → stamp head.
    if "DuplicateTableError" in combined or "already exists" in combined:
        stamp = _run(list(_Cmd.stamp_head))
        if stamp.returncode == 0:
            logger.warning("Alembic stamp head applied for existing schema")
            return True
        logger.warning("Alembic stamp head failed: %s", (stamp.stderr or stamp.stdout).strip())
        return False

    # 4. Unrecoverable — log and let the app boot.
    logger.warning("Alembic upgrade failed (stdout=%s, stderr=%s)", stdout, stderr)
    return False
