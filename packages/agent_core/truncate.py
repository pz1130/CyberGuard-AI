"""Directional tool-output truncation (M0a-2).

Dual constraints — **whichever binds first wins**:
  * ``max_chars`` (character count)
  * ``max_lines`` (newline-separated lines)

Modes:
  * ``"tail"`` — drop the **end** (keep head). Default; good when the lead
    summary matters and a long dump follows.
  * ``"head"`` — drop the **start** (keep tail). Use for logs / scanners where
    the critical signal is at the bottom.

Exit criterion: tail content with key info is not discarded when mode=head.
"""
from __future__ import annotations

from typing import Literal, Optional

TruncateMode = Literal["head", "tail"]


def truncate_text(
    text: Optional[str],
    *,
    mode: TruncateMode = "tail",
    max_chars: Optional[int] = 8000,
    max_lines: Optional[int] = None,
) -> str:
    """Truncate ``text`` under char and/or line caps.

    If both caps are set, apply the tighter result (shorter surviving body).
    ``None`` / empty input → ``""``.
    """
    if text is None:
        return ""
    if not text:
        return text

    candidates = [text]

    if max_lines is not None and max_lines >= 0:
        lines = text.splitlines(keepends=True)
        if len(lines) > max_lines:
            if mode == "head":
                kept = lines[-max_lines:] if max_lines > 0 else []
                dropped = len(lines) - max_lines
                body = "".join(kept)
                marker = f"…[truncated {dropped} lines from head]\n"
                candidates.append(marker + body if body else marker.rstrip("\n"))
            else:
                kept = lines[:max_lines] if max_lines > 0 else []
                dropped = len(lines) - max_lines
                body = "".join(kept)
                marker = f"\n…[truncated {dropped} lines from tail]"
                candidates.append(body.rstrip("\n") + marker)

    if max_chars is not None and max_chars >= 0 and len(text) > max_chars:
        if max_chars == 0:
            candidates.append(f"…[truncated {len(text)} chars]")
        elif mode == "head":
            kept = text[-max_chars:]
            dropped = len(text) - max_chars
            candidates.append(f"…[truncated {dropped} chars from head]\n" + kept)
        else:
            kept = text[:max_chars]
            dropped = len(text) - max_chars
            candidates.append(kept + f"\n…[truncated {dropped} chars from tail]")

    # Pick the shortest candidate that is still a truncation of original
    # (or original if nothing applied). Prefer truncated forms when shorter.
    return min(candidates, key=len)


def truncate_tool_result(
    text: Optional[str],
    *,
    max_chars: int = 8000,
    max_lines: Optional[int] = None,
    mode: TruncateMode = "tail",
) -> str:
    """Back-compat wrapper used by run_loop / InternalAgentRunner."""
    return truncate_text(
        text, mode=mode, max_chars=max_chars, max_lines=max_lines
    )
