"""Frozen demo-set scorer — evaluation without inventing thresholds."""
from pathlib import Path

from app.services.eval_frozen import load_expected_alert_priority, score_alert_ranking

ROOT = Path(__file__).resolve().parents[1]


def test_expected_priorities_match_manifest_csv():
    expected = load_expected_alert_priority(ROOT / "demo" / "alerts.csv")
    assert expected["ALT-001"] == "P1"
    assert expected["ALT-004"] == "P1"
    assert expected["ALT-005"] == "P4"
    assert len(expected) == 5


def test_perfect_ranking_is_full_agreement():
    expected = load_expected_alert_priority(ROOT / "demo" / "alerts.csv")
    result = score_alert_ranking(expected, expected)
    assert result["total"] == 5
    assert result["matched"] == 5
    assert result["agreement"] == 1.0
    assert result["mismatches"] == []


def test_wrong_priority_is_counted():
    assigned = {
        "ALT-001": "P1",
        "ALT-002": "P1",  # expected P2
        "ALT-003": "P3",
        "ALT-004": "P1",
        "ALT-005": "P4",
    }
    result = score_alert_ranking(assigned, load_expected_alert_priority(ROOT / "demo" / "alerts.csv"))
    assert result["matched"] == 4
    assert result["agreement"] == 0.8
    assert result["mismatches"] == [{"alert_id": "ALT-002", "assigned": "P1", "expected": "P2"}]
