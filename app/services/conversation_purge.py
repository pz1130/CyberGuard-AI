"""Dispose of conversations whose retention period has passed.

The safety property of this module is an ordering, not a check: a conversation
is purgeable only when an export object holds *every* one of its messages. A
deployment that cannot archive therefore cannot delete.

Every message of a conversation goes, or none. Deleting the older half would
leave the oldest survivor's ``prev_hash`` pointing at a row that no longer
exists, and ``verify_conversation_chain`` could no longer tell retention apart
from tampering.

The ``conversations`` row survives, carrying ``purged_at`` and ``export_key``.
Round 1's chain anchors name that conversation in the global audit log, and
they must continue to resolve.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage

logger = logging.getLogger(__name__)

PURGE_ACTION = "conversation.purged"


async def _eligible(session: AsyncSession, older_than_days: int) -> List[Dict[str, Any]]:
    cutoff = utc_now() - timedelta(days=older_than_days)

    heads = (
        select(ConversationMessage.conversation_id.label("cid"),
               func.max(ConversationMessage.seq).label("head_seq"),
               func.count(ConversationMessage.id).label("rows"))
        .group_by(ConversationMessage.conversation_id)
        .subquery()
    )
    # A complete export: one whose head_seq reaches the conversation's last
    # message. "Exported at some point" would lose everything written since.
    complete = (
        select(ConversationExport.conversation_id.label("cid"),
               func.max(ConversationExport.head_seq).label("exported_head"))
        .group_by(ConversationExport.conversation_id)
        .subquery()
    )

    rows = (await session.execute(
        select(Conversation.id, Conversation.user_id, heads.c.rows,
               ConversationExport.object_key)
        .join(heads, heads.c.cid == Conversation.id)
        .join(complete, complete.c.cid == Conversation.id)
        .join(ConversationExport,
              (ConversationExport.conversation_id == Conversation.id)
              & (ConversationExport.head_seq == complete.c.exported_head))
        .where(Conversation.updated_at < cutoff,
               Conversation.purged_at.is_(None),
               complete.c.exported_head == heads.c.head_seq)
        .order_by(Conversation.id)
    )).all()

    return [{"conversation_id": r[0], "user_id": r[1], "messages": r[2],
             "object_key": r[3]} for r in rows]


async def purge_eligible(
    session: AsyncSession, older_than_days: int, confirm: bool = False,
) -> Dict[str, Any]:
    """Report, and with ``confirm`` also delete, what retention has released.

    Dry runs by default: this is the one irreversible operation in the product
    and it should not be a typo away.
    """
    candidates = await _eligible(session, older_than_days)
    summary: Dict[str, Any] = {
        "dry_run": not confirm,
        "conversations": [
            {"conversation_id": c["conversation_id"], "messages": c["messages"],
             "object_key": c["object_key"]}
            for c in candidates
        ],
        "messages_deleted": 0,
    }
    if not confirm or not candidates:
        return summary

    from app.core.audit import record_action

    deleted = 0
    for candidate in candidates:
        conversation_id = candidate["conversation_id"]
        await session.execute(delete(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id))
        conv = await session.get(Conversation, conversation_id)
        conv.purged_at = utc_now()
        conv.export_key = candidate["object_key"]
        await session.commit()
        deleted += candidate["messages"]

        # After the commit on purpose: a crash between them leaves a purged
        # conversation with no audit row — a visible inconsistency — rather
        # than an audit row claiming a deletion that did not happen.
        await record_action(
            user_id=candidate["user_id"],
            action=PURGE_ACTION,
            action_category="remediate",
            risk_tier="high",
            rollback_possible=False,
            input_data={"conversation_id": conversation_id,
                        "older_than_days": older_than_days},
            output_data={"messages_deleted": candidate["messages"],
                         "object_key": candidate["object_key"]},
        )

    summary["messages_deleted"] = deleted
    logger.info("[conversation_purge] disposed of %d message(s) across %d "
                "conversation(s)", deleted, len(candidates))
    return summary
