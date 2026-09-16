"""Per-conversation hash chain for chat messages.

``audit_logs`` chains globally and pays for it with a single advisory lock that
every write queues behind (``app/core/audit.py:113``). Chat message volume is
orders of magnitude higher, so this chain is scoped to one conversation: a
message links to the previous message *in the same conversation*, and writers
to different conversations never contend.

What that buys and what it does not: the chain proves no message inside a
conversation was altered, reordered or removed. It cannot prove the
conversation itself was not deleted — nothing would be left to be inconsistent.
``app.services.conversation_anchor`` closes that by periodically writing each
chain head into the global audit chain.

Pure and DB-free, like ``app.core.audit_diff``, so the formula can be tested
against the verifier without a database in the way.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional, Sequence

GENESIS = "0" * 64


def _iso(value: Any) -> str:
    """Render a timestamp for hashing.

    The caller passes the value that is (or was) persisted, never a raw input
    string — a digest over something other than the stored value cannot be
    recomputed from the row.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def entry_hash(
    *,
    conversation_id: int,
    seq: int,
    role: str,
    content: str,
    created_at: Any,
    run_id: Optional[str],
    turn_id: Optional[str],
    prev_hash: str,
) -> str:
    """The digest covering everything that makes this message what it is.

    ``backfilled`` is deliberately absent: it describes where the row came
    from, not what was said, and folding it in would make the flag impossible
    to correct later without invalidating the chain.
    """
    body = (
        f"{conversation_id}|{seq}|{role}|{content}|{_iso(created_at)}|"
        f"{run_id or ''}|{turn_id or ''}|{prev_hash}"
    )
    return hashlib.sha256(body.encode()).hexdigest()


def verify_conversation_chain(messages: Sequence[Any]) -> Optional[str]:
    """Describe the first break in one conversation's chain, or None if intact.

    ``messages`` must be the conversation's rows in ascending ``seq`` order.
    Mirrors ``run_event_log.verify_chain``.
    """
    prev = GENESIS
    for expected_seq, message in enumerate(messages):
        if message.seq != expected_seq:
            return f"seq gap: expected {expected_seq}, found {message.seq}"
        if message.prev_hash != prev:
            return f"broken link at seq {message.seq}"
        recomputed = entry_hash(
            conversation_id=message.conversation_id,
            seq=message.seq,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            run_id=message.run_id,
            turn_id=message.turn_id,
            prev_hash=message.prev_hash,
        )
        if recomputed != message.entry_hash:
            return f"content altered at seq {message.seq}"
        prev = message.entry_hash
    return None
