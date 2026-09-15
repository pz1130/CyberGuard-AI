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

## Container runtime hardening

Release images do not run as root. API, Celery, migrate, and tool-runner use
uid/gid `10001`; WebUI nginx uses uid/gid `101` and binds 8080. Compose drops
all capabilities, sets `no-new-privileges:true`, and mounts a read-only root
filesystem for those services. PostgreSQL and Redis still start as root only
long enough for their official entrypoints to gosu, with `cap_drop: ALL` plus
the gosu capabilities. This is process containment, not a substitute for host
TLS, network policy, or secret custody.

## Executable skill scripts

A script inside a skill bundle is inert on import. An admin holding
`skill:script_approve` reviews it and promotes it into a `Tool`, supplying the
risk metadata; from then on it is gated by the same chain as every other tool,
because it is the same object. That permission is deliberately separate from
`skill:write`, so uploading a script and granting it the right to run stay
independently revocable.

The `Tool` pins the sha256 of the bundle it was approved against. Re-importing
the skill with different contents deactivates the tool until it is reviewed
again, so an approval cannot be reused for code nobody read.

Scripts execute in `skill-runner`, a separate container on an `internal: true`
network: no postgres, no redis, no egress, `python3`/`sh` and the standard
library only, and a subprocess environment carrying no token or secret. The
bundle is written to tmpfs per execution and deleted afterwards; the bundle tree
is read-only and a separate scratch directory is the only writable place, so a
script cannot rewrite the code its approval covered.

`api:8000` remains reachable from that segment — compose network membership is
bidirectional and plain compose cannot express a one-way rule — but a script
holds no credential for it, so its reach there is the unauthenticated surface.
This is a known limit, recorded rather than left to be discovered.

See `docs/superpowers/specs/2026-09-15-skill-script-execution-design.md`.

## Data flow review

Before deployment, document for each provider or MCP connection: data classes,
purpose, legal basis, destination, subprocessors, retention, deletion, logging,
and incident contact. Configure egress to match the approved inventory.
