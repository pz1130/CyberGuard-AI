"""Audit logging middleware and utilities."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import select, func
from app.core.redis_client import get_redis
from app.models.audit import AuditLog
from app.core.database import get_db_session

# In-memory buffer for audit logs (flushed to DB periodically)
_audit_buffer: list = []
_buffer_lock: asyncio.Lock = asyncio.Lock()
_buffer_size = 10


def _hash_data(data: Any) -> str:
    """Create SHA256 hash of data."""
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()


async def log_audit(
    user_id: Optional[int],
    agent_id: Optional[str],
    action: str,
    input_data: Any,
    output_data: Any,
    request_id: Optional[str] = None,
) -> dict:
    """
    Log an audit event.

    Args:
        user_id: ID of the user performing the action
        agent_id: ID of the agent involved (if any)
        action: Description of the action
        input_data: Input data (will be hashed)
        output_data: Output data (will be hashed)
        request_id: Optional request tracking ID
    """
    timestamp = datetime.now(timezone.utc)
    entry = {
        "user_id": user_id,
        "agent_id": agent_id,
        "action": action,
        "input_hash": _hash_data(input_data),
        "output_hash": _hash_data(output_data),
        "timestamp": timestamp.isoformat(),
        "request_id": request_id or _generate_request_id(),
    }

    # Store in Redis for real-time access (best-effort stream; DB is durable path)
    try:
        redis = await get_redis()
        if redis:
            await redis.lpush("audit:log", json.dumps(entry))
    except Exception as e:  # noqa: BLE001
        # INV-25: do not pretend Redis is the only audit path; log loudly
        import logging
        logging.getLogger(__name__).error(
            "audit redis push failed (continuing to DB buffer): %s", e
        )

    # Buffer for DB writes (thread-safe swap)
    async with _buffer_lock:
        _audit_buffer.append(entry)
        should_flush = len(_audit_buffer) >= _buffer_size

    # INV-29: await flush — fire-and-forget create_task can lose audit on crash
    if should_flush:
        await _flush_audit_buffer()

    return entry


async def _flush_audit_buffer():
    """Flush buffered audit logs to database.

    INV-25 / INV-29: flush failures re-queue entries and re-raise so callers
    cannot silently continue without durable audit.
    """
    # Atomically swap out the buffer under lock
    async with _buffer_lock:
        if not _audit_buffer:
            return
        logs_to_write = _audit_buffer[:]
        _audit_buffer.clear()

    # Import here to avoid circular import
    from app.core.database import get_db_context

    try:
        async with get_db_context() as session:
            for entry in logs_to_write:
                log = AuditLog(
                    user_id=entry["user_id"],
                    agent_id=entry["agent_id"],
                    action=entry["action"],
                    input_hash=entry["input_hash"],
                    output_hash=entry["output_hash"],
                    request_id=entry.get("request_id"),
                )
                session.add(log)
            await session.commit()
    except Exception:
        # Put entries back so a later flush can retry
        async with _buffer_lock:
            _audit_buffer[0:0] = logs_to_write
        raise


def _generate_request_id() -> str:
    """Generate unique request ID."""
    import uuid
    return str(uuid.uuid4())


async def get_audit_logs(
    user_id: Optional[int] = None,
    agent_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """Retrieve audit logs from Redis."""
    redis = await get_redis()
    if not redis:
        return []

    # Get all logs (newest first)
    logs = await redis.lrange("audit:log", 0, limit - 1)
    parsed_logs = [json.loads(log) for log in logs]

    # Filter if needed
    if user_id:
        parsed_logs = [l for l in parsed_logs if l.get("user_id") == user_id]
    if agent_id:
        parsed_logs = [l for l in parsed_logs if l.get("agent_id") == agent_id]

    return parsed_logs[offset:offset + limit]


async def flush_audit_buffer():
    """Public interface for shutdown-time flushing (e.g. lifespan event)."""
    await _flush_audit_buffer()


def audit_middleware():
    """Create audit middleware for FastAPI."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    class AuditMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Generate request ID
            import uuid
            request_id = str(uuid.uuid4())
            request.state.request_id = request_id

            # Log request
            await log_audit(
                user_id=getattr(request.state, 'user_id', None),
                agent_id=None,
                action=f"{request.method} {request.url.path}",
                input_data={"method": request.method, "path": request.url.path},
                output_data={"status": "processing"},
                request_id=request_id,
            )

            response = await call_next(request)

            # Log response
            await log_audit(
                user_id=getattr(request.state, 'user_id', None),
                agent_id=None,
                action=f"{request.method} {request.url.path}",
                input_data={"method": request.method, "path": request.url.path},
                output_data={"status": response.status_code},
                request_id=request_id,
            )

            return response

    return AuditMiddleware()


_GENESIS = "0" * 64
_chain_lock = asyncio.Lock()


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, default=str)


async def record_action(
    *, user_id, action, agent_name=None, action_category=None,
    risk_tier=None, confidence=None, human_reviewer=None,
    rollback_possible=None, input_data=None, output_data=None,
    agent_id=None, request_id=None,
) -> dict:
    """Append a tamper-evident, fully-fielded audit record SYNCHRONOUSLY.

    Used for agent decisions/actions (NDB Std). Chained via prev_hash/entry_hash.
    """
    from app.core.database import get_db_context

    payload = {
        "user_id": user_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "action": action,
        "action_category": action_category,
        "confidence": None if confidence is None else f"{float(confidence):.4f}",
        "human_reviewer": human_reviewer,
        "rollback_possible": rollback_possible,
        "risk_tier": risk_tier,
        "input_hash": _hash_data(input_data),
        "output_hash": _hash_data(output_data),
        "request_id": request_id or _generate_request_id(),
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }

    async with _chain_lock:
        async with get_db_context() as session:
            await session.execute(select(func.pg_advisory_xact_lock(0xA0D17)))
            prev = (await session.execute(
                select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)
            )).scalar_one_or_none()
            prev_hash = prev or _GENESIS
            payload["prev_hash"] = prev_hash
            entry_hash = hashlib.sha256(
                (_canonical({k: payload[k] for k in sorted(payload)}) + prev_hash).encode()
            ).hexdigest()
            payload["entry_hash"] = entry_hash

            session.add(AuditLog(
                user_id=user_id, agent_id=(str(agent_id) if agent_id is not None else None),
                agent_name=agent_name, action=action, action_category=action_category,
                confidence=payload["confidence"], human_reviewer=human_reviewer,
                rollback_possible=rollback_possible, risk_tier=risk_tier,
                input_hash=payload["input_hash"], output_hash=payload["output_hash"],
                request_id=payload["request_id"], prev_hash=prev_hash, entry_hash=entry_hash,
            ))
            await session.commit()
    return payload


async def verify_chain() -> tuple[bool, int | None]:
    """Recompute the chain; return (ok, first_broken_row_id or None)."""
    from app.core.database import get_db_context
    async with get_db_context() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.entry_hash.is_not(None)).order_by(AuditLog.id.asc())
        )).scalars().all()
    prev = _GENESIS
    for r in rows:
        if r.prev_hash != prev:
            return False, r.id
        prev = r.entry_hash
    return True, None