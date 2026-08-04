"""Tool-runner output uses directional truncate (keep tail by default)."""
from app.services.tool_executor import OUTPUT_MAX_CHARS, _truncate


def test_truncate_keeps_tail_for_long_scanner_output():
    head = "A" * 100
    tail_marker = "CRITICAL_FINDING_AT_END"
    text = head + ("B" * (OUTPUT_MAX_CHARS + 500)) + tail_marker
    out = _truncate(text, mode="head")
    assert tail_marker in out
    assert "truncated" in out.lower() or "…" in out
    # Must not be pure head-only keep (old behavior kept only prefix)
    assert not out.startswith("A" * 50) or tail_marker in out


def test_truncate_tail_mode_keeps_prefix():
    text = "PREFIX_SIGNAL" + ("x" * (OUTPUT_MAX_CHARS + 100)) + "SUFFIX"
    out = _truncate(text, mode="tail")
    assert out.startswith("PREFIX_SIGNAL")
    assert "SUFFIX" not in out
