"""Mirror a whole conversation to write-once object storage.

One object per conversation, not an incremental export keyed on message id.
The chain is per conversation and so is the anchor in the global audit log, so
a conversation is the unit of evidence: an object holding fragments of many
conversations contains no complete chain and can be verified against nothing.

The object carries every field ``entry_hash`` covers, so a reader with nothing
but the file can recompute the chain and compare its head against the
``conversation.chain_anchor`` row in the exported audit log. The two exports
verify each other.

S3 configuration is reused from ``app.services.audit_worm``.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage
from app.services.conversation_chain import verify_conversation_chain

# Everything the chain hashes, so the object can be re-verified on its own.
_MESSAGE_FIELDS = ("seq", "role", "content", "created_at", "run_id", "turn_id",
                   "backfilled", "prev_hash", "entry_hash")


def serialize_conversation(conv: Conversation,
                           messages: List[ConversationMessage]) -> str:
    """JSONL: one header line for the conversation, then one line per message."""
    lines = [json.dumps({
        "type": "conversation",
        "id": conv.id,
        "user_id": conv.user_id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }, sort_keys=True, ensure_ascii=False)]

    for message in messages:
        record: Dict[str, Any] = {"type": "message"}
        for field in _MESSAGE_FIELDS:
            value = getattr(message, field, None)
            record[field] = value.isoformat() if isinstance(value, datetime) else value
        lines.append(json.dumps(record, sort_keys=True, ensure_ascii=False))

    return "\n".join(lines) + "\n"


def _s3_client():
    """Same configuration as the audit WORM export, deliberately."""
    import boto3

    endpoint = os.environ.get("S3_ENDPOINT", os.environ.get("OSS_ENDPOINT", ""))
    access = os.environ.get("S3_ACCESS_KEY", "")
    secret = os.environ.get("S3_SECRET_KEY", "")
    region = os.environ.get("S3_REGION", "us-east-1")
    if not endpoint or not access:
        raise RuntimeError(
            "S3/OSS not configured: set S3_ENDPOINT and S3_ACCESS_KEY. "
            "Nothing can be purged until conversations can be archived.")
    bucket = os.environ.get("CONVERSATION_WORM_BUCKET", "cyberguard-chat-worm")
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access,
                        aws_secret_access_key=secret, region_name=region), bucket


async def _put_worm_object(key: str, data: bytes, retain_until: datetime) -> str:
    def _do():
        client, bucket = _s3_client()
        client.put_object(Bucket=bucket, Key=key, Body=data,
                          ObjectLockMode="COMPLIANCE",
                          ObjectLockRetainUntilDate=retain_until)
        return key
    return await asyncio.to_thread(_do)


async def export_conversation(
    session: AsyncSession, conversation_id: int, retain_days: int,
) -> Dict[str, Any]:
    """Archive one conversation. Returns what happened, rather than raising.

    Re-export is not deduplicated: if the head has not moved, a second call
    writes a second identical object. Suppressing that would mean trusting the
    marker table to decide whether evidence exists, and the marker table is
    mutable while the objects are not.
    """
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        return {"conversation_id": conversation_id, "skipped": "missing"}

    messages = list((await session.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.seq)
    )).scalars().all())

    if not messages:
        # An empty object would assert the conversation was empty at a moment
        # nothing recorded.
        return {"conversation_id": conversation_id, "skipped": "empty"}

    broken = verify_conversation_chain(messages)
    if broken is not None:
        return {"conversation_id": conversation_id,
                "skipped": f"chain-broken: {broken}"}

    head = messages[-1]
    retain_until = utc_now() + timedelta(days=retain_days)
    key = (f"conversations/worm/{conversation_id}-{head.seq}-"
           f"{utc_now():%Y%m%dT%H%M%SZ}.jsonl")

    object_key = await _put_worm_object(
        key, serialize_conversation(conv, messages).encode(), retain_until)

    session.add(ConversationExport(
        conversation_id=conversation_id, object_key=object_key,
        rows=len(messages), head_seq=head.seq, head_hash=head.entry_hash,
        retain_until=retain_until, exported_at=utc_now()))

    return {"conversation_id": conversation_id, "object_key": object_key,
            "rows": len(messages), "head_seq": head.seq,
            "head_hash": head.entry_hash}


async def export_eligible(
    session: AsyncSession, older_than_days: int, retain_days: int,
) -> Dict[str, Any]:
    """Archive every conversation last updated before the cutoff.

    One conversation's failure is recorded and the rest proceed: a single
    corrupt chain must not cost every other conversation its archive.
    """
    cutoff = utc_now() - timedelta(days=older_than_days)
    ids = list((await session.execute(
        select(Conversation.id)
        .where(Conversation.updated_at < cutoff,
               Conversation.purged_at.is_(None))
        .order_by(Conversation.id)
    )).scalars().all())

    exported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for conversation_id in ids:
        result = await export_conversation(session, conversation_id, retain_days)
        (skipped if "skipped" in result else exported).append(result)

    return {"exported": exported, "skipped": skipped}
