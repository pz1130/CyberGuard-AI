"""Startup report for agent runs a crash left mid-flight.

``agent_run_events`` records ``tool_execution/start`` before the tool runs, so
a run that dispatched a scan and then died leaves a row saying so. On boot we
scan the recent window, verify each chain, and log what we find.

Replaying a side-effecting tool is **never** automatic. Only ``replay=safe``
unresolved calls are even candidates, and even then this only marks the run for
operator attention — deciding to re-run something is a human's call, and the
whole point of the record is that we do not know whether the action landed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def sweep_interrupted_runs(*, limit: int = 50) -> List[Dict[str, Any]]:
    """Find interrupted runs, log them, and return the report for callers/UI."""
    from app.services.run_event_log import find_interrupted_runs

    runs = await find_interrupted_runs(limit=limit)
    if not runs:
        logger.info("run recovery: no interrupted runs in the recent window")
        return []

    safe = [r for r in runs if r.get("safe_to_replay") and not r.get("chain_error")]
    logger.warning(
        "run recovery: %d interrupted run(s) — %d safe-to-replay candidates, "
        "%d require operator review",
        len(runs), len(safe), len(runs) - len(safe),
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
