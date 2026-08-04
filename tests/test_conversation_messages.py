"""Conversation messages_json append helpers (multi-worker RMW safety)."""
from __future__ import annotations

from app.services.conversation_messages import (
    parse_messages,
    serialize_messages,
    stamp_message,
)


def test_parse_messages_tolerates_garbage():
    assert parse_messages(None) == []
    assert parse_messages("not-json") == []
    assert parse_messages('{"a":1}') == []  # object, not list
    assert parse_messages('[{"role":"user","content":"hi"}]') == [
        {"role": "user", "content": "hi"}
    ]


def test_serialize_roundtrip():
    msgs = [{"role": "user", "content": "你好"}]
    raw = serialize_messages(msgs)
    assert "你好" in raw
    assert parse_messages(raw) == msgs


def test_stamp_message_adds_created_at():
    m = stamp_message({"role": "assistant", "content": "ok"})
    assert "created_at" in m
    assert m["role"] == "assistant"
    # does not overwrite existing timestamp
    fixed = stamp_message({"role": "user", "content": "x", "created_at": "t0"})
    assert fixed["created_at"] == "t0"


def test_append_logic_preserves_order():
    """Simulate two sequential locked appends (unit-level, no DB)."""
    existing = parse_messages("[]")
    existing.append(stamp_message({"role": "user", "content": "a"}))
    existing.append(stamp_message({"role": "assistant", "content": "b"}))
    existing.append(stamp_message({"role": "user", "content": "c"}))
    raw = serialize_messages(existing)
    again = parse_messages(raw)
    assert [m["content"] for m in again] == ["a", "b", "c"]
