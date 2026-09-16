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

## Manual Syslog export

The Audit Logs page's **SYSLOG** button sends the latest 10,000 audit records
from the backend to a supplied hostname/IP and port. This is a manual batch
export; it does not save configuration or continuously forward new records.
Existing local downloads remain available.

`POST /api/v1/audit/export/syslog` requires `audit:read` (admin or auditor):

```json
{"host":"syslog.example.com","port":514,"protocol":"tcp","facility":16}
```

Protocols: `tcp` (default) or `udp`; ports: 1–65535; facility: 0–23
(default local0/16; the UI offers local0–local7). IPv6 addresses are entered
without brackets, with the port supplied separately. No TLS is provided.
The backend must have network access to the collector.

Each record is an [RFC 5424](https://www.rfc-editor.org/rfc/rfc5424.html)
message with informational severity, app-name `cyberguard`, msgid `audit`,
and a JSON body containing identifiers, action, UTC timestamp, request ID,
and hash-chain fields. TCP uses
[RFC 6587 octet-counting](https://www.rfc-editor.org/rfc/rfc6587.html).
UDP sends one record per datagram.

Success returns `sent`, `total`, and `protocol`. Sending only confirms local
transport writes, not collector ingestion (especially with UDP). The export
has a 30-second timeout. Connection/write failures return HTTP 502 with
`detail.sent` and `detail.total`; earlier records may already have arrived.
There is no automatic retry; repeating an export can create duplicate records,
which receivers can identify by record ID and entry hash.
