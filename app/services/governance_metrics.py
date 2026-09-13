"""Read-only governance metrics (NDB Std §POC Success Criteria)."""
from __future__ import annotations
import time
from datetime import datetime, timedelta
from sqlalchemy import select, func
from app.core.time import utc_now

_TARGETS = {
    "governance_violation_rate":    (0.005, lambda v, t: v < t),
    "human_override_rate":          (0.10,  lambda v, t: v < t),
    "kill_switch_response_seconds": (3.0,   lambda v, t: v < t),
    "audit_completeness":           (1.0,   lambda v, t: v >= t),
    "rollback_success_rate":        (0.99,  lambda v, t: v > t),
}


def _verdict(name: str, value: float) -> bool:
    target, cmp = _TARGETS[name]
    return cmp(value, target)


def _rate(num: int, denom: int) -> float:
    return 0.0 if denom == 0 else num / denom


def _since(window_days: int) -> datetime:
    return utc_now() - timedelta(days=window_days)


async def _governance_violation_rate(window_days: int) -> float:
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    since = _since(window_days)
    async with get_db_context() as s:
        total = (await s.execute(select(func.count()).select_from(AuditLog).where(
            AuditLog.action.like("gatekeeper:%"), AuditLog.timestamp >= since))).scalar() or 0
        denied = (await s.execute(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "gatekeeper:deny", AuditLog.timestamp >= since))).scalar() or 0
    return _rate(denied, total)


async def _human_override_rate(window_days: int) -> float:
    from app.core.database import get_db_context
    from app.models.approval import ApprovalRequest
    since = _since(window_days)
    async with get_db_context() as s:
        decided = (await s.execute(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.status.in_(("approved", "rejected")),
            ApprovalRequest.created_at >= since))).scalar() or 0
        rejected = (await s.execute(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.status == "rejected", ApprovalRequest.created_at >= since))).scalar() or 0
    return _rate(rejected, decided)


async def _kill_switch_response(window_days: int) -> float:
    """Synthetic probe: time from engage() to is_halted() reflecting it."""
    from app.services import kill_switch as ks
    probe = "agent:__metrics_probe__"
    await ks.clear(probe)
    t0 = time.monotonic()
    await ks.engage(probe, by="metrics", reason="response probe")
    elapsed = 99.0
    for _ in range(60):
        if await ks.is_halted(agent_id="__metrics_probe__"):
            elapsed = time.monotonic() - t0
            break
        time.sleep(0.05)
    await ks.clear(probe)
    return round(elapsed, 3)


async def _audit_completeness(window_days: int) -> float:
    from app.core.audit import verify_chain
    ok, _ = await verify_chain()
    return 1.0 if ok else 0.0


async def _rollback_success_rate(window_days: int) -> float:
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    since = _since(window_days)
    async with get_db_context() as s:
        reverted = (await s.execute(select(func.count()).select_from(RollbackRegistration).where(
            RollbackRegistration.status == "reverted", RollbackRegistration.created_at >= since))).scalar() or 0
        failed = (await s.execute(select(func.count()).select_from(RollbackRegistration).where(
            RollbackRegistration.status == "failed", RollbackRegistration.created_at >= since))).scalar() or 0
    total = reverted + failed
    return 1.0 if total == 0 else _rate(reverted, total)


async def collect(window_days: int = 30) -> dict:
    values = {
        "governance_violation_rate":    await _governance_violation_rate(window_days),
        "human_override_rate":          await _human_override_rate(window_days),
        "kill_switch_response_seconds": await _kill_switch_response(window_days),
        "audit_completeness":           await _audit_completeness(window_days),
        "rollback_success_rate":        await _rollback_success_rate(window_days),
    }
    metrics = [{"name": n, "value": v, "target": _TARGETS[n][0], "pass": _verdict(n, v)}
               for n, v in values.items()]
    return {"window_days": window_days, "metrics": metrics,
            "all_pass": all(m["pass"] for m in metrics)}
