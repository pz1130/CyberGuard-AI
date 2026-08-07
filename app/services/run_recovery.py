"""Startup recovery for interrupted agent runs (audit #24 follow-up).

``agent_run_events`` is append-only and already records ``tool_started`` before
execution. On boot we scan for runs that never finished, verify their hash
chain, and log a structured report. Replaying side-effecting tools is never
automatic — only ``replay=safe`` unresolved calls are candidates, and even
then we only mark the run for operator attention.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def sweep_interrupted_runs(*, limit: int = 50) -> List[Dict[str, Any]]:
    """Find interrupted runs, log them, return the report for callers/UI."""
    from app.services.run_event_log import find_interrupted_runs

    try:
        runs = await find_interrupted_runs(limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("run recovery: find_interrupted_runs failed: %s", e)
        return []

    if not runs:
        logger.info("run recovery: no interrupted runs")
        return []

    safe = [r for r in runs if r.get("safe_to_replay") and not r.get("chain_error")]
    unsafe = [r for r in runs if not r.get("safe_to_replay") or r.get("chain_error")]

    logger.warning(
        "run recovery: %d interrupted run(s) — %d safe-to-replay candidates, "
        "%d require operator review",
        len(runs), len(safe), len(unsafe),
    )
    for r in runs:
        logger.warning(
            "run recovery: run_id=%s agent_id=%s last_seq=%s safe=%s chain=%s "
            "unresolved=%s",
            r.get("run_id"), r.get("agent_id"), r.get("last_seq"),
            r.get("safe_to_replay"), r.get("chain_error"),
            r.get("unresolved_tool_calls"),
        )
    return runs
