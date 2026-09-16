"""The per-conversation hash chain, as arithmetic — no database involved.

The chain is what turns a transcript into evidence, so the hash function and
the verifier have to agree exactly. Testing them against each other here, with
plain objects, means a later failure in a DB test is a storage bug and not a
disagreement about the formula.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.conversation_chain import (
    GENESIS,
    entry_hash,
    verify_conversation_chain,
)

T0 = datetime(2026, 9, 16, 12, 0, 0)


def _row(seq, content, prev_hash, *, conversation_id=7, role="user",
         created_at=T0, run_id=None, turn_id=None, entry=None):
    digest = entry or entry_hash(
        conversation_id=conversation_id, seq=seq, role=role, content=content,
        created_at=created_at, run_id=run_id, turn_id=turn_id, prev_hash=prev_hash,
    )
    return SimpleNamespace(
        conversation_id=conversation_id, seq=seq, role=role, content=content,
        created_at=created_at, run_id=run_id, turn_id=turn_id,
        prev_hash=prev_hash, entry_hash=digest,
    )


def _chain(*contents, conversation_id=7):
    """A transcript: roles alternate, as they do in a real conversation."""
    rows, prev = [], GENESIS
    for seq, content in enumerate(contents):
        row = _row(seq, content, prev, conversation_id=conversation_id,
                   role="user" if seq % 2 == 0 else "assistant")
        rows.append(row)
        prev = row.entry_hash
    return rows


def test_genesis_matches_the_other_chains_in_this_codebase():
    from app.core.audit import _GENESIS as audit_genesis
    from app.services.run_event_log import _GENESIS as run_genesis
    assert GENESIS == audit_genesis == run_genesis


def test_an_intact_chain_verifies():
    assert verify_conversation_chain(_chain("hello", "hi", "bye")) is None


def test_an_empty_conversation_verifies():
    assert verify_conversation_chain([]) is None


def test_altering_content_is_detected_and_named():
    rows = _chain("hello", "hi", "bye")
    rows[1].content = "something the AI never said"
    assert verify_conversation_chain(rows) == "content altered at seq 1"


def test_altering_the_role_is_detected():
    """Re-attributing an assistant answer to the user is exactly the forgery
    this chain exists to catch."""
    rows = _chain("hello", "hi")
    assert rows[1].role == "assistant"
    rows[1].role = "user"
    assert verify_conversation_chain(rows) == "content altered at seq 1"


def test_altering_the_timestamp_is_detected():
    rows = _chain("hello", "hi")
    rows[1].created_at = datetime(2020, 1, 1)
    assert verify_conversation_chain(rows) == "content altered at seq 1"


def test_a_removed_message_is_detected():
    rows = _chain("a", "b", "c")
    assert verify_conversation_chain([rows[0], rows[2]]) == "seq gap: expected 1, found 2"


def test_a_reordered_pair_is_detected():
    rows = _chain("a", "b")
    assert verify_conversation_chain([rows[1], rows[0]]) == "seq gap: expected 0, found 1"


def test_a_relinked_row_is_detected():
    """Re-chaining a forged row to the right predecessor still fails, because
    the successor's prev_hash no longer matches."""
    rows = _chain("a", "b", "c")
    rows[1] = _row(1, "forged", rows[0].entry_hash)
    assert verify_conversation_chain(rows) == "broken link at seq 2"


def test_the_first_row_must_link_to_genesis():
    rows = _chain("a", "b")
    rows[0].prev_hash = "f" * 64
    assert verify_conversation_chain(rows) == "broken link at seq 0"


def test_two_conversations_do_not_share_a_chain():
    """The same text at the same seq in two conversations must hash
    differently, or a message could be moved between transcripts."""
    a = _chain("identical", conversation_id=1)
    b = _chain("identical", conversation_id=2)
    assert a[0].entry_hash != b[0].entry_hash


def test_a_datetime_and_its_isoformat_hash_alike():
    """The store hashes the datetime it persists; the backfill migration hashes
    the datetime it parsed. They must land on the same digest."""
    common = dict(conversation_id=1, seq=0, role="user", content="x",
                  run_id=None, turn_id=None, prev_hash=GENESIS)
    assert entry_hash(created_at=T0, **common) == entry_hash(
        created_at=T0.isoformat(), **common)


def test_run_and_turn_ids_are_covered():
    common = dict(conversation_id=1, seq=0, role="assistant", content="x",
                  created_at=T0, turn_id=None, prev_hash=GENESIS)
    assert entry_hash(run_id="run-a", **common) != entry_hash(run_id="run-b", **common)


def test_absent_correlation_ids_hash_as_empty_not_as_the_word_none():
    """`None` rendering as the literal "None" would let a message with the
    literal string run id "None" collide with one that has no run id."""
    common = dict(conversation_id=1, seq=0, role="user", content="x",
                  created_at=T0, turn_id=None, prev_hash=GENESIS)
    assert entry_hash(run_id=None, **common) != entry_hash(run_id="None", **common)
