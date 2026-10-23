"""Read-only audit diagnostics. Hash consistency is not external authenticity."""
from __future__ import annotations

from app.core.audit import _GENESIS, _CHAIN_VERSION, _row_chain_payload, stamp_chain_hashes


def inspect_rows(rows, *, previous_hash=_GENESIS, limit=100):
    issues = []
    counts = dict(link_mismatches=0, payload_mismatches=0, unsigned_rows=0,
                  legacy_rows=0, unsupported_rows=0, verified_rows=0)
    first = None
    signed = 0
    affected = 0
    prev = previous_hash
    for row in rows:
        if not row.entry_hash:
            counts['unsigned_rows'] += 1
            continue
        signed += 1
        reasons = []
        if row.prev_hash != prev:
            counts['link_mismatches'] += 1
            reasons.append('link_mismatch')
        if row.chain_version == _CHAIN_VERSION:
            expected = stamp_chain_hashes(_row_chain_payload(row), row.prev_hash or '')['entry_hash']
            if expected != row.entry_hash:
                counts['payload_mismatches'] += 1
                reasons.append('payload_mismatch')
            elif not reasons:
                counts['verified_rows'] += 1
        elif row.chain_version in (None, 1):
            counts['legacy_rows'] += 1
        else:
            counts['unsupported_rows'] += 1
        if reasons:
            affected += 1
            if first is None:
                first = row.id
            if len(issues) < limit:
                issues.append({'row_id': row.id, 'reasons': reasons,
                               'action': row.action,
                               'timestamp': (row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else row.timestamp) if row.timestamp else None})
        prev = row.entry_hash
    intact = first is None
    incomplete = counts['unsigned_rows'] + counts['legacy_rows'] + counts['unsupported_rows']
    status = 'broken' if not intact else 'empty' if not rows else 'partial' if incomplete else 'verified'
    return {'intact': intact, 'fully_verified': status == 'verified', 'status': status,
            'first_broken_row_id': first, 'total_rows': len(rows), 'signed_rows': signed,
            **counts, 'issues': issues, 'issues_truncated': affected > len(issues), 'affected_rows': affected,
            'head_row_id': rows[-1].id if rows else None,
            'head_hash': prev if signed else None,
            'scope': 'database_snapshot', 'external_authenticity_verified': False}


async def inspect_chain():
    from sqlalchemy import select
    from app.core.database import get_db_context
    from app.models.audit import AuditLog
    async with get_db_context() as session:
        rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    return inspect_rows(rows)
