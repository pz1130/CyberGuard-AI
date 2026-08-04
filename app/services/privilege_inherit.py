"""INV-21 · Cross-agent privilege inheritance.

Target agent effective privilege must not exceed the current execution
context. LLM-driven dispatch is capped (default medium/L2) so prompt
injection cannot escalate into a high-permission agent. User-explicit
selection and expert fan-out are trusted contexts (user is the authority).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


PERMISSION_RANK = {"low": 0, "medium": 1, "high": 2}
# Unknown levels rank as medium (neither free pass nor total block).
_DEFAULT_PERM = "medium"
_DEFAULT_TIER = "L2"

# Master context when the *user* chose the agent (UI pick / expert mode).
TRUSTED_CONTEXT_PERMISSION = "high"
TRUSTED_CONTEXT_AUTONOMY = "L3"

# Master context when the *LLM intent parser* chose the agent (injection surface).
LLM_CONTEXT_PERMISSION = "medium"
LLM_CONTEXT_AUTONOMY = "L2"

# Anonymous local fallback (no AgentConfig row) — treat as medium/L2.
UNBOUND_TARGET_PERMISSION = "medium"
UNBOUND_TARGET_AUTONOMY = "L2"

DISPATCH_USER_EXPLICIT = "user_explicit"
DISPATCH_USER_EXPERT = "user_expert"
DISPATCH_LLM = "llm"
DISPATCH_AGENT = "agent"  # future: one sub-agent spawning another


@dataclass(frozen=True)
class PrivilegeSnapshot:
    """Comparable privilege of a context or target agent."""

    permission_level: str = _DEFAULT_PERM
    autonomy_tier: str = _DEFAULT_TIER
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None

    def perm_rank(self) -> int:
        return PERMISSION_RANK.get(
            str(self.permission_level or _DEFAULT_PERM).lower(),
            PERMISSION_RANK[_DEFAULT_PERM],
        )

    def tier_rank(self) -> int:
        raw = str(self.autonomy_tier or _DEFAULT_TIER).strip().upper()
        if raw.startswith("L") and raw[1:].isdigit():
            return int(raw[1:])
        try:
            return int(raw)
        except ValueError:
            return int(_DEFAULT_TIER[1:])


def normalize_permission(level: Optional[str]) -> str:
    key = str(level or _DEFAULT_PERM).lower()
    return key if key in PERMISSION_RANK else _DEFAULT_PERM


def normalize_tier(tier: Optional[str]) -> str:
    raw = str(tier or _DEFAULT_TIER).strip().upper()
    if raw.startswith("L") and raw[1:].isdigit():
        return f"L{int(raw[1:])}"
    if raw.isdigit():
        return f"L{int(raw)}"
    return _DEFAULT_TIER


def snapshot_from_mapping(
    data: Optional[Mapping[str, Any]],
    *,
    default_perm: str = _DEFAULT_PERM,
    default_tier: str = _DEFAULT_TIER,
) -> PrivilegeSnapshot:
    """Build a snapshot from an AgentConfig-like dict."""
    data = data or {}
    aid = data.get("id") or data.get("agent_id")
    try:
        aid_int = int(aid) if aid is not None else None
    except (TypeError, ValueError):
        aid_int = None
    return PrivilegeSnapshot(
        permission_level=normalize_permission(
            data.get("permission_level") or default_perm
        ),
        autonomy_tier=normalize_tier(data.get("autonomy_tier") or default_tier),
        agent_id=aid_int,
        agent_name=data.get("agent_name"),
    )


def context_for_dispatch_source(
    source: Optional[str],
    *,
    # Optional override when a sub-agent is the caller (nested dispatch).
    caller: Optional[PrivilegeSnapshot] = None,
    llm_max_permission: str = LLM_CONTEXT_PERMISSION,
    llm_max_autonomy: str = LLM_CONTEXT_AUTONOMY,
) -> PrivilegeSnapshot:
    """Resolve the *source* privilege for a dispatch decision."""
    src = (source or DISPATCH_LLM).lower()
    if src in (DISPATCH_USER_EXPLICIT, DISPATCH_USER_EXPERT):
        return PrivilegeSnapshot(
            permission_level=TRUSTED_CONTEXT_PERMISSION,
            autonomy_tier=TRUSTED_CONTEXT_AUTONOMY,
        )
    if src == DISPATCH_AGENT:
        if caller is None:
            # No caller snapshot → refuse to invent privilege; use LLM cap.
            return PrivilegeSnapshot(
                permission_level=normalize_permission(llm_max_permission),
                autonomy_tier=normalize_tier(llm_max_autonomy),
            )
        return caller
    # llm (default) and anything unknown → capped
    return PrivilegeSnapshot(
        permission_level=normalize_permission(llm_max_permission),
        autonomy_tier=normalize_tier(llm_max_autonomy),
    )


def check_dispatch(
    source: PrivilegeSnapshot,
    target: PrivilegeSnapshot,
) -> Tuple[bool, str]:
    """INV-21: allow only when target privilege ≤ source on every axis.

    Returns (allowed, reason). reason is stable for tests/audit.
    """
    if target.perm_rank() > source.perm_rank():
        return (
            False,
            (
                f"permission_level target={target.permission_level} "
                f"> source={source.permission_level}"
            ),
        )
    if target.tier_rank() > source.tier_rank():
        return (
            False,
            (
                f"autonomy_tier target={target.autonomy_tier} "
                f"> source={source.autonomy_tier}"
            ),
        )
    return True, "ok"


def unbound_target_snapshot() -> PrivilegeSnapshot:
    """Privilege assumed for local-by-type fallback without AgentConfig."""
    return PrivilegeSnapshot(
        permission_level=UNBOUND_TARGET_PERMISSION,
        autonomy_tier=UNBOUND_TARGET_AUTONOMY,
    )
