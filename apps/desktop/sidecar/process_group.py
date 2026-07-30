"""Process-group + parent-death watchdog for orphan governance (M1).

Three layers (design §3):
  1. setsid / process group — killpg on shutdown
  2. ppid watchdog — if reparented to 1, cleanup + exit
  3. Electron SIGTERM on before-quit (main process)

M1 tracks child PIDs (MCP stubs); real MCP spawn lands on the same registry.
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import threading
import time
from typing import Dict, Optional, Set

logger = logging.getLogger("cyberguard.desktop.process_group")


class ProcessRegistry:
    """Tracks child PIDs and tears them down with the sidecar."""

    def __init__(self) -> None:
        self._children: Dict[int, str] = {}  # pid -> label
        self._lock = threading.Lock()
        self._watchdog_stop = threading.Event()
        self._watchdog: Optional[threading.Thread] = None
        self._pgid: Optional[int] = None

    def become_session_leader(self) -> None:
        """Best-effort new session/process group (INV orphan layer ①)."""
        try:
            os.setsid()
            self._pgid = os.getpgrp()
            logger.info("setsid ok pgid=%s", self._pgid)
        except OSError as exc:
            # Already a leader, or not allowed (e.g. some test harnesses)
            self._pgid = os.getpgrp()
            logger.info("setsid skipped (%s); pgid=%s", exc, self._pgid)

    def register(self, pid: int, label: str = "child") -> None:
        with self._lock:
            self._children[pid] = label
        logger.info("registered child pid=%s label=%s", pid, label)

    def unregister(self, pid: int) -> None:
        with self._lock:
            self._children.pop(pid, None)

    def child_pids(self) -> Set[int]:
        with self._lock:
            return set(self._children.keys())

    def kill_all(self, *, sig: int = signal.SIGTERM) -> None:
        """Terminate registered children, then process group if we lead one."""
        with self._lock:
            pids = list(self._children.items())
        for pid, label in pids:
            try:
                os.kill(pid, sig)
                logger.info("sent signal %s to pid=%s (%s)", sig, pid, label)
            except ProcessLookupError:
                pass
            except OSError as exc:
                logger.warning("kill pid=%s failed: %s", pid, exc)
        # Group kill (covers unregistered grandchildren that stayed in pg)
        if self._pgid is not None and self._pgid != 0:
            try:
                os.killpg(self._pgid, sig)
            except ProcessLookupError:
                pass
            except OSError as exc:
                # Killing our own group may raise if we are the only member
                logger.debug("killpg: %s", exc)
        with self._lock:
            self._children.clear()

    def start_watchdog(self, interval_sec: float = 2.0) -> None:
        """Layer ②: if PPID becomes 1, Electron is gone — cleanup and exit."""
        if self._watchdog and self._watchdog.is_alive():
            return

        def _loop() -> None:
            while not self._watchdog_stop.wait(interval_sec):
                try:
                    ppid = os.getppid()
                except OSError:
                    ppid = 1
                if ppid <= 1:
                    logger.error(
                        "parent dead (ppid=%s) — orphan cleanup and exit", ppid
                    )
                    self.kill_all(sig=signal.SIGTERM)
                    time.sleep(0.2)
                    self.kill_all(sig=signal.SIGKILL)
                    os._exit(1)

        self._watchdog = threading.Thread(
            target=_loop, name="ppid-watchdog", daemon=True
        )
        self._watchdog.start()

    def stop_watchdog(self) -> None:
        self._watchdog_stop.set()

    def install_atexit(self) -> None:
        atexit.register(lambda: self.kill_all(sig=signal.SIGTERM))


# Process-wide singleton used by MCP manager + main
REGISTRY = ProcessRegistry()
