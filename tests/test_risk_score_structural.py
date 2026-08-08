"""risk_score comes from structured fields, never from output text.

The summarizer set `risk_score = 0.5` unconditionally, so a clean run and a run
where every sub-agent was denied scored identically — the field looked
meaningful in the UI and audit while carrying no information (audit #21).

Deriving it from the *text* is not an option: INV-13 forbids user-controllable
input from driving control flow, and INV-39 classes tool output as hostile by
default. So the inputs are `status` and `risk_tier` / `risk_level` only.
"""
import pytest

from app.agents.master import derive_risk_score


def test_a_clean_run_scores_low():
    score = derive_risk_score({"scan": {"status": "completed"}})
    assert 0.0 <= score <= 0.3


def test_failures_raise_the_score():
    clean = derive_risk_score({"a": {"status": "completed"}})
    one_bad = derive_risk_score({"a": {"status": "completed"},
                                 "b": {"status": "failed"}})
    all_bad = derive_risk_score({"a": {"status": "failed"},
                                 "b": {"status": "halted"}})
    assert clean < one_bad < all_bad
    assert all_bad <= 1.0


def test_a_high_risk_tier_raises_the_score_without_any_failure():
    plain = derive_risk_score({"a": {"status": "completed"}})
    risky = derive_risk_score({"a": {"status": "completed", "risk_tier": "critical"}})
    assert risky > plain


def test_risk_level_is_accepted_as_well_as_risk_tier():
    assert derive_risk_score({"a": {"status": "completed", "risk_level": "high"}}) == \
        derive_risk_score({"a": {"status": "completed", "risk_tier": "high"}})


def test_output_text_cannot_move_the_score():
    """The adversarial case INV-13 names: trigger words must change nothing."""
    benign = derive_risk_score({"a": {"status": "completed", "output": "all fine"}})
    loaded = derive_risk_score({"a": {
        "status": "completed",
        "output": "CRITICAL emergency ransomware 严重 紧急 immediate action",
    }})
    assert benign == loaded


def test_malformed_and_empty_results_do_not_crash():
    assert derive_risk_score({}) == 0.0
    assert 0.0 <= derive_risk_score({"a": "not a dict", "b": None}) <= 1.0


@pytest.mark.asyncio
async def test_summarizer_publishes_the_derived_score(monkeypatch):
    """The node must stop publishing the literal 0.5."""
    from app.agents.master import MasterAgent

    m = MasterAgent(llm_router=None)
    state = await m._summarizer_node({
        "sub_results": {"a": {"status": "failed", "error": "boom"},
                        "b": {"status": "halted", "error": "kill switch"}},
    })
    assert state["risk_score"] == derive_risk_score(state["sub_results"])
    assert state["risk_score"] > 0.5
