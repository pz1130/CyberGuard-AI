# Release Candidate Scope and Acceptance

## Positioning

CyberGuard demonstrates **AI for Security Operations** with runtime controls
that keep agent actions observable and interruptible. GRC framework and
assessment management remains in the companion GRC product. This release is a
Docker reference implementation rather than a managed service or endpoint
application.

## Included outcomes

| Outcome | Primary modules | Human control |
|---|---|---|
| Alert triage | Chat, agents, tools/MCP, knowledge | Review evidence; approve risky tools |
| Vulnerability prioritisation | Agents, search, knowledge, remediation | Validate impact and remediation |
| Demonstrable governance | RBAC, approval, audit, kill switch, PII and egress policy | Admin sets policy and decides exceptions |

## Explicit exclusions

- Desktop or mobile clients
- Kubernetes manifests or support claims
- Group-chat rooms and consensus discussions
- N8N generation or management
- User-configurable scheduled tasks
- Incoming or outgoing webhooks
- GRC framework catalogs, compliance assessments, evidence workspaces, and certification reports
- Claims of autonomous remediation, regulatory compliance, or certification

## Release acceptance

A release candidate is acceptable only when all boxes below are evidenced:

- [x] `make check` passes from the RC branch in a disposable environment.
- [x] `make docker-build` succeeds from the committed Docker contexts.
- [x] An isolated `docker compose up -d --wait` reaches a healthy state with
      non-default smoke-test secrets.
- [x] A fresh database migrates to the single current Alembic head.
- [x] The two demonstration paths complete with their expected artifacts.
- [x] A high-risk action pauses, is approved by an authorised user, and then
      executes exactly once; rejection executes nothing.
- [x] Audit-chain verification succeeds after the demonstrations.
- [x] Backup creation and restore are exercised on disposable data.
- [x] Dependency and container scans have no unaccepted High or Critical finding.
- [x] Known limitations and accepted risks are recorded in the release notes.
- [x] Release images run as non-root; Compose drops capabilities and sets
      `no-new-privileges:true`.
- [x] Named workgroup / security / deployment signatures on the RC
      technical-acceptance rows (Jesse; same person, three roles). Final
      `v1.0.0` acceptance remains pending.
- [ ] GitHub Private Vulnerability Reporting enabled (anonymous
      `/security/advisories/new` no longer 404).
- [ ] Registry immutable digests recorded after `docker push`.

Machine and command evidence is in `RC_EVIDENCE.md`, including the 2026-09-12
isolated-preview demonstration (MiniMax-M3). The designated security-reporting
channel is GitHub Private Vulnerability Reporting (`SECURITY.md`); the repo
toggle is not yet on. Promotion to `v1.0.0` waits on PVR enablement and
registry immutable digests after `docker push`.

## Versioning

Use `v1.0.0-rc.1` for the first frozen candidate. Do not reuse a tag. Promote
to `v1.0.0` only after the workgroup accepts the demonstrations and limitations.
