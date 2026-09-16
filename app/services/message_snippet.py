"""The fragment a search result shows in place of the message body.

Search results carry a snippet rather than the message, because one long
transcript would otherwise dominate a page of results and the pane renders a
single preview line anyway.

Pure and DB-free, like ``app.core.audit_diff`` and
``app.services.conversation_chain``.
"""
from __future__ import annotations

SNIPPET_CHARS = 200
_ELLIPSIS = "…"


def snippet(content: str, term: str) -> str:
    """At most ``SNIPPET_CHARS`` characters of ``content``, centred on ``term``.

    Sliced by character, not byte: a CJK character is three bytes in UTF-8 and
    a byte slice would cut one in half.
    """
    if not content:
        return ""
    if len(content) <= SNIPPET_CHARS:
        return content

    index = content.lower().find(term.lower()) if term else -1
    if index < 0:
        # Only reachable if the row changed between matching and reading. The
        # opening of the message is more useful than an error.
        return content[:SNIPPET_CHARS] + _ELLIPSIS

    half = (SNIPPET_CHARS - len(term)) // 2
    start = max(0, index - half)
    end = min(len(content), start + SNIPPET_CHARS)
    # Re-extend leftwards when the hit sits near the end, so the window stays
    # the full width instead of trailing off short.
    start = max(0, end - SNIPPET_CHARS)

    out = content[start:end]
    if start > 0:
        out = _ELLIPSIS + out
    if end < len(content):
        out = out + _ELLIPSIS
    return out
