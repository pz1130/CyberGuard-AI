"""Pure row-building for migration 041's backfill.

Separated from the migration so it can be tested. The migration calls it and
does the inserting; nothing here touches a database.

Kept after the migration ships: it is what the migration's meaning depends on,
and re-deriving it from a changed chain formula later would silently produce
rows that no longer verify.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.conversation_chain import GENESIS, entry_hash


def _naive_utc(value: Any) -> Optional[datetime]:
    """Parse an ISO timestamp into the naive-UTC form this codebase stores."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def rows_for_conversation(
    conversation_id: int,
    messages_json: Optional[str],
    fallback_created_at: datetime,
) -> List[Dict[str, Any]]:
    """Chained, `backfilled`-flagged rows for one conversation's blob.

    A blob that will not parse yields nothing: a migration that fails on one
    malformed row would block the whole deployment, and the blob is still on
    the conversation row for anyone who wants to look at it.
    """
    try:
        parsed = json.loads(messages_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []

    rows: List[Dict[str, Any]] = []
    prev_hash = GENESIS
    seq = 0
    for message in parsed:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")[:32]
        content = message.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        created_at = _naive_utc(message.get("created_at")) or fallback_created_at
        digest = entry_hash(
            conversation_id=conversation_id, seq=seq, role=role, content=content,
            created_at=created_at, run_id=None, turn_id=None, prev_hash=prev_hash,
        )
        rows.append({
            "conversation_id": conversation_id, "seq": seq, "role": role,
            "content": content, "run_id": None, "turn_id": None,
            "created_at": created_at, "backfilled": True,
            "prev_hash": prev_hash, "entry_hash": digest,
        })
        prev_hash = digest
        seq += 1
    return rows
