"""Unit tests for master validation scoring (audit #21)."""
from app.agents.validation import score_results, detect_high_risk, extract_action_items


def test_failed_status_fails_validation():
    passed, errors, risk, items, approval = score_results({
        "a": {"status": "failed", "error": "boom"},
    })
    assert passed is False
    assert any("boom" in e for e in errors)
    assert risk >= 0.5


def test_needs_approval_does_not_fail_but_flags_approval():
    passed, errors, risk, items, approval = score_results({
        "a": {"status": "needs_approval", "output": None},
    })
    assert passed is True
    assert approval is True


def test_chinese_high_risk_keywords_detected():
    hits = detect_high_risk(["发现严重漏洞，需要紧急处理"])
    assert hits
    _, _, _, _, approval = score_results({
        "a": {"status": "completed", "output": "发现严重漏洞，需要紧急处理"},
    })
    assert approval is True


def test_english_critical_flags_approval():
    _, _, risk, _, approval = score_results({
        "a": {"status": "completed", "output": "CRITICAL finding requires immediate action"},
    })
    assert approval is True
    assert risk > 0.2


def test_action_items_extracted_from_recommendation():
    items = extract_action_items(["Recommendation: patch OpenSSL within 24 hours."])
    assert items
    assert any("patch" in i.lower() or "openssl" in i.lower() for i in items)


def test_clean_run_has_low_risk():
    passed, errors, risk, items, approval = score_results({
        "a": {"status": "completed", "output": "all ports closed, no issues"},
    })
    assert passed is True
    assert not errors
    assert approval is False
    assert risk <= 0.3
    assert items
