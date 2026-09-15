"""Bundle digest — what makes an approval bind to specific code."""
from __future__ import annotations

import pytest

from app.services.skill_bundle import bundle_digest, file_bytes


def test_digest_is_stable_and_order_independent():
    a = bundle_digest([("b.txt", b"two"), ("a.txt", b"one")])
    b = bundle_digest([("a.txt", b"one"), ("b.txt", b"two")])
    assert a == b
    assert len(a) == 64 and a == a.lower()


def test_digest_changes_when_any_content_changes():
    before = bundle_digest([("scripts/x.py", b"print(1)")])
    after = bundle_digest([("scripts/x.py", b"print(2)")])
    assert before != after


def test_digest_covers_siblings_not_just_the_entrypoint():
    # A python entrypoint can import a sibling; hashing only the entrypoint
    # would leave the real payload unprotected.
    before = bundle_digest([("scripts/x.py", b"import helper"), ("scripts/helper.py", b"ok")])
    after = bundle_digest([("scripts/x.py", b"import helper"), ("scripts/helper.py", b"evil")])
    assert before != after


def test_digest_changes_when_a_file_is_added_or_removed():
    one = bundle_digest([("a", b"x")])
    two = bundle_digest([("a", b"x"), ("b", b"")])
    assert one != two


def test_length_prefixing_prevents_boundary_collisions():
    # Without length prefixes, "ab" + "c" and "a" + "bc" would hash alike.
    left = bundle_digest([("ab", b"c")])
    right = bundle_digest([("a", b"bc")])
    assert left != right


def test_file_bytes_reads_text_and_blob_rows():
    class Row:
        def __init__(self, text, blob):
            self.content_text, self.content_blob = text, blob

    assert file_bytes(Row("hello", None)) == b"hello"
    assert file_bytes(Row(None, b"\x00\x01")) == b"\x00\x01"
    assert file_bytes(Row(None, None)) == b""
