"""Score frozen RC demonstration rankings against the labelled CSV."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Mapping


def load_expected_alert_priority(csv_path: Path) -> Dict[str, str]:
    expected: Dict[str, str] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aid = (row.get("alert_id") or "").strip()
            pri = (row.get("expected_priority") or "").strip()
            if aid and pri:
                expected[aid] = pri
    return expected


def score_alert_ranking(
    assigned: Mapping[str, str],
    expected: Mapping[str, str],
) -> dict:
    mismatches: List[dict] = []
    matched = 0
    for aid, exp in expected.items():
        got = assigned.get(aid)
        if got == exp:
            matched += 1
        else:
            mismatches.append({"alert_id": aid, "assigned": got, "expected": exp})
    total = len(expected)
    return {
        "total": total,
        "matched": matched,
        "agreement": (matched / total) if total else 0.0,
        "mismatches": mismatches,
    }
