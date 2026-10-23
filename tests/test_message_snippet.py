"""The fragment a search result shows instead of the whole message.

Returning message bodies would let one long transcript dominate a page of
results, and the pane only renders a single preview line. Centring on the hit
is what makes the result readable: a match 4000 characters into an answer is
useless if the snippet starts at character zero.
"""
from __future__ import annotations

from app.services.message_snippet import SNIPPET_CHARS, snippet


def test_a_short_message_is_returned_whole():
    assert snippet("three open ports", "ports") == "three open ports"


def test_a_short_message_gains_no_ellipsis():
    assert "…" not in snippet("three open ports", "ports")


def test_the_snippet_is_centred_on_the_hit():
    content = ("a" * 1000) + "NEEDLE" + ("b" * 1000)
    out = snippet(content, "needle")
    assert "NEEDLE" in out
    assert len(out) <= SNIPPET_CHARS + 2  # plus the two ellipses
    assert out.startswith("…") and out.endswith("…")


def test_a_hit_near_the_start_does_not_pad_the_left():
    content = "NEEDLE" + ("b" * 1000)
    out = snippet(content, "needle")
    assert out.startswith("NEEDLE"), "no leading ellipsis when nothing was cut"
    assert out.endswith("…")


def test_a_hit_near_the_end_does_not_pad_the_right():
    content = ("a" * 1000) + "NEEDLE"
    out = snippet(content, "needle")
    assert out.startswith("…")
    assert out.endswith("NEEDLE")


def test_matching_ignores_case():
    assert "Ports" in snippet("three open Ports here", "PORTS")


def test_chinese_content_is_measured_in_characters_not_bytes():
    """A CJK character is three bytes in UTF-8; slicing by bytes would cut one
    in half and produce mojibake."""
    content = ("甲" * 500) + "开放端口" + ("乙" * 500)
    out = snippet(content, "开放端口")
    assert "开放端口" in out
    assert len(out) <= SNIPPET_CHARS + 2


def test_no_hit_falls_back_to_the_opening():
    """Only reachable if the row changed between matching and reading. A
    snippet is not worth raising over."""
    out = snippet("a" * 1000, "nothing here")
    assert out.startswith("a")
    assert len(out) <= SNIPPET_CHARS + 1


def test_an_empty_term_does_not_raise():
    assert isinstance(snippet("some content", ""), str)


def test_empty_content_is_empty():
    assert snippet("", "anything") == ""
