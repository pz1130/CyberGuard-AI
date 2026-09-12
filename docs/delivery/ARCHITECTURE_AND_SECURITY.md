# Architecture and Security

## Trust boundaries

The browser is untrusted input. FastAPI authenticates users and applies RBAC.
PostgreSQL stores configuration, conversations, and audit data. Redis provides
coordination and rate-limit state. Celery runs
background agent work. The tool-runner is isolated on the Compose network and
accepts only authenticated, structured execution requests.

External LLM and MCP endpoints are separate trust domains. Their use must be
covered by deployment-specific allowlists and data-handling decisions.

## Principal controls

- Password hashing and optional Entra ID SSO
- AES-256-GCM authenticated encryption for stored credentials
- Prompt-injection detection and input sanitisation
- PII redaction/blocking and secrets detection
- Structured risk categories, confidence gates, and human approval
- Cross-agent privilege inheritance and fan-out limits
- Kill switch and safety-envelope/rollback registration
- SSRF checks and optional egress allowlist
- HTTP, action, and run-event audit records with chain verification
- Encrypted backup and controlled restore

## Important boundaries

An application-level audit chain is tamper-evident, not external WORM storage.
Encrypted credentials do not protect a running process that is already
compromised. Approval reduces agent error but is only separation of duties when
the approver is organisationally independent. A deployment must supply TLS,
host hardening, monitoring, backup custody, and provider governance.

## Data flow review

Before deployment, document for each provider or MCP connection: data classes,
purpose, legal basis, destination, subprocessors, retention, deletion, logging,
and incident contact. Configure egress to match the approved inventory.
