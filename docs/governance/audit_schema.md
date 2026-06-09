# Audit Record Schema (NDB Std §Audit Trail)

Every governed decision/action is written by `app/core/audit.py::record_action()`
to the append-only, hash-chained `audit_logs` table.

| Field | Type | Meaning |
|-------|------|---------|
| timestamp | datetime (UTC) | when recorded |
| agent_name | string | agent that acted |
| action | string | e.g. `gatekeeper:allow`, `EMERGENCY_HALT`, `pii_redaction` |
| action_category | string | observe/annotate/notify/contain_soft/contain_hard/remediate/mutate |
| confidence | string(float) | model confidence at decision |
| human_reviewer | string\|null | approver id/email when applicable |
| rollback_possible | bool\|null | whether a rollback was registered |
| risk_tier | string | critical/high/medium/low |
| input_hash / output_hash | sha256 | tamper-evident content hashes |
| request_id | uuid | correlation id |
| prev_hash / entry_hash | sha256 | hash chain (verify via `GET /audit/verify`) |

Integrity: deletion is forbidden (no delete endpoint; DB delete grant revoked in prod).
Tamper-evidence: `entry_hash = sha256(canonical(record) || prev_hash)`; `GET /audit/verify`
recomputes the chain and reports the first broken row, if any.
