# Governance Test Results (Red Team)

Machine-checkable evidence: `tests/test_governance_redteam.py` (+ `test_gatekeeper.py`,
`test_pii.py`, `test_safety_envelope.py`). Run:

    .venv/bin/python -m pytest tests/test_governance_redteam.py -v

| Attack / forbidden path | Expected control | Test |
|-------------------------|------------------|------|
| `mutate` in POC | gatekeeper DENY | test_redteam_mutate_blocked_in_poc |
| action above autonomy tier | gatekeeper DENY | test_redteam_action_above_autonomy_blocked |
| contain/remediate w/o rollback | gatekeeper DENY | test_redteam_contain_without_rollback_blocked |
| low-confidence action | escalate to human | test_redteam_low_confidence_escalated |
| any action while halted | gatekeeper DENY | test_redteam_halt_blocks_everything |
| secret sent to LLM | blocked pre-call | test_redteam_secret_blocked_before_llm |
| PII sent to LLM | redacted pre-call | test_redteam_pii_redacted_before_llm |

Live metrics for the Success Criteria: `GET /api/v1/governance/metrics`.
