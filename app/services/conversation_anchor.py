"""Write each conversation's chain head into the global audit chain.

``conversation_chain`` gives each conversation its own chain, which is what
keeps chat writes off the global audit advisory lock. The cost of that choice
is that a chain proves nothing about its own existence: delete every row of one
and nothing is left to be inconsistent.

This periodically records a head — conversation id, head seq, head hash — as an
ordinary audit row. One row per *active* conversation per interval, not per
message, which is the volume the global lock can absorb.

What it does not cover: messages appended after the last anchor and removed
before the next. That window is the schedule, not the design.
"""
from __future__ import annotations

import logging
from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_action_sync
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

logger = logging.getLogger(__name__)

ANCHOR_ACTION = "conversation.chain_anchor"


def anchor_pending(session: Session, *, limit: int = 500) -> Dict[str, int]:
    """Anchor every conversation whose head has moved since it was last anchored."""
    heads = (
        select(
            ConversationMessage.conversation_id.label("cid"),
            func.max(ConversationMessage.seq).label("head_seq"),
        )
        .group_by(ConversationMessage.conversation_id)
        .subquery()
    )
    pending = session.execute(
        select(Conversation, heads.c.head_seq)
        .join(heads, heads.c.cid == Conversation.id)
        .where(heads.c.head_seq > Conversation.last_anchored_seq)
        .order_by(Conversation.id)
        .limit(limit)
    ).all()

    anchored = 0
    for conv, head_seq in pending:
        head = session.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.seq == head_seq,
            )
        ).scalar_one_or_none()
        if head is None:
            # The head moved between the two queries; the next run catches it.
            continue

        backfilled_through = session.execute(
            select(func.max(ConversationMessage.seq)).where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.backfilled.is_(True),
            )
        ).scalar_one_or_none()

        # The audit row is written first and the marker advanced second: if the
        # process dies between them the next run writes a duplicate anchor,
        # which is harmless. The other order would lose one silently.
        record_action_sync(
            user_id=conv.user_id,
            action=ANCHOR_ACTION,
            action_category="annotate",
            rollback_possible=False,
            input_data={
                "conversation_id": conv.id,
                "from_seq": conv.last_anchored_seq + 1,
            },
            output_data={
                "head_seq": head.seq,
                "head_hash": head.entry_hash,
                "backfilled_through": backfilled_through,
            },
        )
        conv.last_anchored_seq = head.seq
        anchored += 1

    if anchored:
        logger.info("[conversation_anchor] anchored %d conversation chain(s)", anchored)
    return {"anchored": anchored}
