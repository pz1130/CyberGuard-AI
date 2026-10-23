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
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_path: Optional[str] = None,
    metadata: Optional[dict] = None,
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
        ip_address / user_agent / request_path / metadata: stored verbatim

    input_data and output_data are hashed, which makes them tamper-evidence
    material rather than something you can query. The columns below are the
    ones an investigator actually filters on ("what did this IP do", "which
    calls 403'd"), so they are stored as-is. They already existed on the model
    and were simply never written.
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
        "ip_address": ip_address,
        "user_agent": (user_agent or None) and str(user_agent)[:500],
        "request_path": (request_path or None) and str(request_path)[:500],
        "metadata": metadata,
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


async def _clear_deleted_actors(session, entries: list) -> None:
    """Blank the actor on entries whose user no longer exists.

    Persisted audit actors are protected by a restrictive foreign key. An entry
    still sitting in the buffer had no such protection: the insert violated the
    constraint, and because a failed flush re-queues its entries and re-raises
    (INV-25/29, so that nothing is lost), the entry could never succeed and
    every later flush failed with it. Three consecutive logins returning 500,
    not recovering, was the observed result of deleting a user who had just
    signed in.

    A user without persisted audit references can still disappear before a
    buffered entry is flushed. Clear that missing actor before signing so the
    resulting entry remains valid; never change actors on persisted entries.
    """
    from app.models.user import User

    actors = {e["user_id"] for e in entries if e.get("user_id") is not None}
    if not actors:
        return
    alive = set((await session.execute(
        select(User.id).where(User.id.in_(actors)))).scalars().all())
    for entry in entries:
        if entry.get("user_id") is not None and entry["user_id"] not in alive:
            entry["user_id"] = None


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
        async with _chain_lock:
            async with get_db_context() as session:
                await session.execute(select(func.pg_advisory_xact_lock(0xA0D17)))
                # Before the chain payload is built: the actor is part of the
                # hash, so clearing it afterwards would store a row that does
                # not match the hash stored beside it.
                await _clear_deleted_actors(session, logs_to_write)
                prev = (await session.execute(
                    select(AuditLog.entry_hash)
                    .where(AuditLog.entry_hash.is_not(None))
                    .order_by(AuditLog.id.desc())
                    .limit(1)
                )).scalar_one_or_none()
                prev_hash = prev or _GENESIS
                for entry in logs_to_write:
                    entry_timestamp = datetime.fromisoformat(entry["timestamp"]).replace(tzinfo=None)
                    chain_payload = _chain_payload(
                        user_id=entry["user_id"], agent_id=entry["agent_id"],
                        action=entry["action"], input_hash=entry["input_hash"],
                        output_hash=entry["output_hash"], request_id=entry.get("request_id"),
                        timestamp=entry_timestamp, ip_address=entry.get("ip_address"),
                        user_agent=entry.get("user_agent"), request_path=entry.get("request_path"),
                        metadata_json=entry.get("metadata"),
                    )
                    stamped = stamp_chain_hashes(chain_payload, prev_hash)
                    prev_hash = stamped["entry_hash"]
                    log = AuditLog(
                        user_id=entry["user_id"],
                        agent_id=entry["agent_id"],
                        action=entry["action"],
                        input_hash=entry["input_hash"],
                        output_hash=entry["output_hash"],
                        request_id=entry.get("request_id"),
                        # .get(): entries buffered by an older process may predate
                        # these keys, and a flush must never fail on that.
                        ip_address=entry.get("ip_address"),
                        user_agent=entry.get("user_agent"),
                        request_path=entry.get("request_path"),
                        metadata_json=entry.get("metadata"),
                        timestamp=entry_timestamp,
                        prev_hash=stamped["prev_hash"],
                        entry_hash=stamped["entry_hash"],
                        chain_version=_CHAIN_VERSION,
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
_CHAIN_VERSION = 2
_chain_lock = asyncio.Lock()


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, default=str)


def stamp_chain_hashes(payload: dict, prev_hash: str) -> dict:
    """Return a copy of payload with prev_hash/entry_hash filled."""
    stamped = dict(payload)
    stamped["prev_hash"] = prev_hash
    body = {k: stamped[k] for k in sorted(stamped) if k != "entry_hash"}
    stamped["entry_hash"] = hashlib.sha256(
        (_canonical(body) + prev_hash).encode()
    ).hexdigest()
    return stamped


def _chain_payload(
    *, user_id=None, agent_id=None, agent_name=None, action=None,
    action_category=None, confidence=None, human_reviewer=None,
    rollback_possible=None, risk_tier=None, input_hash=None,
    output_hash=None, request_id=None, timestamp=None, ip_address=None,
    user_agent=None, request_path=None, metadata_json=None,
) -> dict:
    """Build the complete persisted payload protected by chain version 2."""
    if isinstance(timestamp, datetime):
        timestamp = timestamp.replace(tzinfo=None).isoformat()
    return {
        "user_id": user_id,
        "agent_id": str(agent_id) if agent_id is not None else None,
        "agent_name": agent_name,
        "action": action,
        "action_category": action_category,
        "confidence": confidence,
        "human_reviewer": human_reviewer,
        "rollback_possible": rollback_possible,
        "risk_tier": risk_tier,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "request_id": request_id,
        "timestamp": timestamp,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "request_path": request_path,
        "metadata_json": metadata_json,
        "chain_version": _CHAIN_VERSION,
    }


def _row_chain_payload(row: AuditLog) -> dict:
    return _chain_payload(
        user_id=row.user_id, agent_id=row.agent_id, agent_name=row.agent_name,
        action=row.action, action_category=row.action_category,
        confidence=row.confidence, human_reviewer=row.human_reviewer,
        rollback_possible=row.rollback_possible, risk_tier=row.risk_tier,
        input_hash=row.input_hash, output_hash=row.output_hash,
        request_id=row.request_id, timestamp=row.timestamp,
        ip_address=row.ip_address, user_agent=row.user_agent,
        request_path=row.request_path, metadata_json=row.metadata_json,
    )


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

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = _chain_payload(
        user_id=user_id, agent_id=agent_id, agent_name=agent_name, action=action,
        action_category=action_category,
        confidence=None if confidence is None else f"{float(confidence):.4f}",
        human_reviewer=human_reviewer, rollback_possible=rollback_possible,
        risk_tier=risk_tier, input_hash=_hash_data(input_data),
        output_hash=_hash_data(output_data), request_id=request_id or _generate_request_id(),
        timestamp=timestamp,
    )

    async with _chain_lock:
        async with get_db_context() as session:
            await session.execute(select(func.pg_advisory_xact_lock(0xA0D17)))
            prev = (await session.execute(
                select(AuditLog.entry_hash)
                .where(AuditLog.entry_hash.is_not(None))
                .order_by(AuditLog.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            prev_hash = prev or _GENESIS
            payload = stamp_chain_hashes(payload, prev_hash)
            entry_hash = payload["entry_hash"]

            session.add(AuditLog(
                user_id=user_id, agent_id=(str(agent_id) if agent_id is not None else None),
                agent_name=agent_name, action=action, action_category=action_category,
                confidence=payload["confidence"], human_reviewer=human_reviewer,
                rollback_possible=rollback_possible, risk_tier=risk_tier,
                input_hash=payload["input_hash"], output_hash=payload["output_hash"],
                request_id=payload["request_id"], prev_hash=prev_hash, entry_hash=entry_hash,
                timestamp=timestamp, chain_version=_CHAIN_VERSION,
            ))
            await session.commit()
    return payload


def record_action_sync(
    *, user_id, action, agent_name=None, action_category=None,
    risk_tier=None, confidence=None, human_reviewer=None,
    rollback_possible=None, input_data=None, output_data=None,
    agent_id=None, request_id=None,
) -> dict:
    """Sync twin of ``record_action``, for Celery workers.

    Celery tasks in this codebase use ``get_sync_session`` rather than bridging
    into the async engine (see ``cleanup_stale_executions_task``), and the same
    reasoning gives ``conversation_messages`` a sync append twin.

    ``_chain_lock`` has no counterpart here, and needs none: it only serialises
    coroutines inside one event loop. ``pg_advisory_xact_lock`` is what makes
    the chain correct across processes, and that is taken below.
    """
    from app.core.database import get_sync_session

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    payload = _chain_payload(
        user_id=user_id, agent_id=agent_id, agent_name=agent_name, action=action,
        action_category=action_category,
        confidence=None if confidence is None else f"{float(confidence):.4f}",
        human_reviewer=human_reviewer, rollback_possible=rollback_possible,
        risk_tier=risk_tier, input_hash=_hash_data(input_data),
        output_hash=_hash_data(output_data),
        request_id=request_id or _generate_request_id(), timestamp=timestamp,
    )

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        session.execute(select(func.pg_advisory_xact_lock(0xA0D17)))
        prev = session.execute(
            select(AuditLog.entry_hash)
            .where(AuditLog.entry_hash.is_not(None))
            .order_by(AuditLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        prev_hash = prev or _GENESIS
        payload = stamp_chain_hashes(payload, prev_hash)

        session.add(AuditLog(
            user_id=user_id, agent_id=(str(agent_id) if agent_id is not None else None),
            agent_name=agent_name, action=action, action_category=action_category,
            confidence=payload["confidence"], human_reviewer=human_reviewer,
            rollback_possible=rollback_possible, risk_tier=risk_tier,
            input_hash=payload["input_hash"], output_hash=payload["output_hash"],
            request_id=payload["request_id"], prev_hash=prev_hash,
            entry_hash=payload["entry_hash"], timestamp=timestamp,
            chain_version=_CHAIN_VERSION,
        ))
        session.commit()
    return payload


async def verify_chain() -> tuple[bool, int | None]:
    """Compatibility wrapper: only full v2 payload coverage passes."""
    from app.services.audit_integrity import inspect_chain
    report = await inspect_chain()
    return report['fully_verified'], report['first_broken_row_id']
