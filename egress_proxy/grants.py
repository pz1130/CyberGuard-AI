"""Per-execution egress grants.

A grant is the whole authorization: it names one execution's allowlist and
expires with that execution. Nothing here is persisted — a proxy restart
drops every grant, and scripts lose network rather than gaining it.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple


def host_allowed(host: str, allowlist: Sequence[str]) -> bool:
    """Exact match, or suffix match for a leading-dot entry.

    Same rule as ``app/core/egress.py``; reimplemented because this package
    cannot import from ``app``.

    The leading dot is what keeps the suffix match on a label boundary:
    ``.vendor.example`` covers ``api.vendor.example`` and the bare domain, but
    not ``evilvendor.example``.
    """
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        return False
    for raw in allowlist or ():
        entry = (raw or "").strip().lower().rstrip(".")
        if not entry:
            continue
        if entry.startswith("."):
            bare = entry[1:]
            if name == bare or name.endswith(entry):
                return True
        elif name == entry:
            return True
    return False


class GrantStore:
    """nonce -> (allowlist, expiry). In-memory, single process (see spec §4)."""

    def __init__(self, now: Optional[Callable[[], float]] = None) -> None:
        self._now = now or time.monotonic
        self._grants: Dict[str, Tuple[List[str], float]] = {}

    def grant(self, nonce: str, allowlist: List[str], ttl: float) -> None:
        self._grants[nonce] = (list(allowlist), self._now() + float(ttl))

    def revoke(self, nonce: str) -> None:
        self._grants.pop(nonce, None)

    def lookup(self, nonce: str) -> Optional[List[str]]:
        entry = self._grants.get(nonce)
        if not entry:
            return None
        allowlist, expiry = entry
        if self._now() > expiry:
            self._grants.pop(nonce, None)
            return None
        return allowlist

    def purge(self) -> None:
        now = self._now()
        for nonce in [n for n, (_a, exp) in self._grants.items() if now > exp]:
            self._grants.pop(nonce, None)
