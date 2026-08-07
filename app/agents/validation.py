"""Pure validation helpers for the master agent.

Kept free of I/O so unit tests can exercise the scoring rules without a
database or LLM. The master node's job is to call these and write results
into graph state.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# High-risk signals in either English or Chinese. Matched as whole-ish phrases
# so common words like "drop" inside "backdrop" don't fire.
_HIGH_RISK_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bcritical\b",
        r"\bemergency\b",
        r"\bimmediate action\b",
        r"\bransomware\b",
        r"\bdata breach\b",
        r"\bzero[- ]day\b",
        r"\bprivilege escalation\b",
        r"严重|紧急|立即处理|立刻处置|勒索软件|数据泄露|零日|提权",
    )
]

_ACTION_ITEM_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(?:recommend(?:ed|ation)?|should|must|需要|建议|请)[:：\s]+(.{8,120})",
        r"(?:action item|next step|下一步)[:：\s]+(.{8,120})",
    )
]


def collect_outputs(sub_results: Dict[Any, Any]) -> List[str]:
    texts: List[str] = []
    for result in (sub_results or {}).values():
        if not isinstance(result, dict):
            continue
        out = result.get("output")
        if out is None:
            continue
        texts.append(str(out))
    return texts


def detect_high_risk(texts: List[str]) -> List[str]:
    hits: List[str] = []
    for text in texts:
        for pat in _HIGH_RISK_PATTERNS:
            if pat.search(text or ""):
                hits.append(pat.pattern)
                break
    return hits


def extract_action_items(texts: List[str], *, limit: int = 5) -> List[str]:
    items: List[str] = []
    seen = set()
    for text in texts:
        for pat in _ACTION_ITEM_PATTERNS:
            for match in pat.finditer(text or ""):
                item = match.group(1).strip().rstrip("。.;；")
                key = item.lower()
                if item and key not in seen:
                    seen.add(key)
                    items.append(item)
                    if len(items) >= limit:
                        return items
    return items


def score_results(sub_results: Dict[Any, Any]) -> Tuple[bool, List[str], float, List[str], bool]:
    """Return (passed, errors, risk_score, action_items, approval_required_by_risk).

    * ``passed`` is False when any sub-result has status ``failed`` or ``halted``.
    * ``needs_approval`` does **not** fail validation — it sets the approval
      flag via the caller (the tool did not run; the graph must pause).
    * ``risk_score`` is in ``[0, 1]`` derived from failure rate + high-risk hits.
    """
    errors: List[str] = []
    needs_approval = False
    n = max(len(sub_results or {}), 1)
    failed = 0

    for agent_id, result in (sub_results or {}).items():
        if not isinstance(result, dict):
            errors.append(f"Agent {agent_id}: malformed result")
            failed += 1
            continue
        status = (result.get("status") or "").lower()
        if status == "failed":
            errors.append(f"Agent {agent_id} failed: {result.get('error') or 'unknown error'}")
            failed += 1
        elif status == "halted":
            errors.append(f"Agent {agent_id} halted: {result.get('error') or 'kill switch'}")
            failed += 1
        elif status == "needs_approval":
            needs_approval = True

    texts = collect_outputs(sub_results)
    risk_hits = detect_high_risk(texts)
    if risk_hits:
        needs_approval = True

    fail_ratio = failed / n
    risk_bonus = min(0.4, 0.15 * len(risk_hits))
    # Base 0.2 for clean runs; climb with failures and risk language.
    risk_score = round(min(1.0, 0.2 + 0.6 * fail_ratio + risk_bonus), 3)

    action_items = extract_action_items(texts)
    if not action_items:
        if failed:
            action_items = ["Review failed agent outputs and re-run after fixing the cause"]
        elif risk_hits:
            action_items = ["Review high-risk findings with a human operator"]
        else:
            action_items = ["Review agent outputs"]

    passed = failed == 0
    return passed, errors, risk_score, action_items, needs_approval
