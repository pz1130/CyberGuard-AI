# RC Verification Evidence

Candidate: `1.0.0-rc.1`  
Branch: `codex/release-candidate`  
Verification date: 2026-09-14 (Asia/Shanghai)

## Delivery model

This is a source-only Docker delivery. Reviewers build the API, tool-runner,
and WebUI images inside their own controlled environment. Registry publication
and registry digests are optional and are not release conditions. The durable
delivery identity is the immutable Git tag and the SHA-256 of its source
archive.

## Automated gate

- `make check`: backend 620 passed, 0 skipped; frontend 8 passed;
  frontend type check covers app and tests (`tsconfig.app.json` and
  `tsconfig.test.json`); lint ratchet passed (eslint baseline 0 errors /
  0 warnings, including test files); production npm audit reported 0
  vulnerabilities.
- Fresh Alembic migration: `036_knowledge_provider_binding (head)`, with one head.
- Compose configuration validation: passed with explicit non-default secrets.
- Release image build: API, tool-runner, and WebUI built successfully.
- Container scan: `make security-scan` (HIGH,CRITICAL, ignore-unfixed) passed
  on the rebuilt images — 0 High, 0 Critical in API, tool-runner, and WebUI.
- 2026-09-13 hardening rebuild: images run as `10001:10001` / nginx `101:101`;
  Compose `cap_drop: ALL` and `no-new-privileges:true`; app services
  `read_only: true`. Isolated preview recreated healthy. `make security-scan`
  on the hardened images still 0 High / 0 Critical.
- 2026-09-14 rebuild after HTTP-audit fail-closed, frontend test gates, and
  theme/lang boot changes. `make check` on this tree: backend 620 passed,
  frontend 8 passed. `make docker-build` then `make security-scan`
  (HIGH,CRITICAL, ignore-unfixed): 0 High / 0 Critical on all three images.
- 2026-09-14 source-delivery closeout: `make rc-check` passed as a single
  command without requiring a local `.env`: backend 620 passed, frontend 8
  passed, Compose validated, all three ARM64 images rebuilt, all three scans
  reported 0 High / 0 Critical, and all three SBOMs were regenerated. Fixed
  check-only values are used only for Compose interpolation and are not baked
  into images or accepted for runtime startup.
- 2026-09-14 GitHub Actions release gate passed on commit
  `ea1e67cb17c2e21b35575233fb7a2a865f580cbb`: all tests and checks passed,
  the three release images were built and runtime-tested on Linux AMD64,
  container scans reported no unaccepted High or Critical findings, and the
  three CycloneDX SBOMs were uploaded as the
  `cyberguard-1.0.0-rc.1-sbom` workflow artifact.

## Runtime smoke test

An isolated Compose preview with separate ports was started with
`docker compose up -d --wait`. PostgreSQL, Redis, API, tool-runner, Celery
worker, Celery beat, and WebUI reached their expected running/healthy states.
The following checks passed:

- `/health` returned version `1.0.0-rc.1`.
- `/health/ready` reported PostgreSQL and Redis healthy.
- The explicitly configured bootstrap administrator could sign in.
- A conversation override could be saved and then cleared with explicit JSON
  `null`; the update returned HTTP 200 and PostgreSQL persisted both cleared
  fields.
- The OpenAPI surface contains no GRC Assessment, Group Chat, Schedule, N8N,
  or Webhook route.
- The WebUI root returned HTTP 200.
- A fresh-database cold start with four API workers created exactly one
  bootstrap administrator, eight built-in Prompt templates, two demo tools,
  one demo skill, and one demo agent, with no seed race or duplicate-key log.
- The Master Agent persisted `MiniMax` Provider ID `34` together with the exact
  verified model name `MiniMax-M3`; a cross-provider model save returned 400.
- A live streamed chat completed through that Master Agent selection, including
  provider reasoning tags handled by the collapsed WebUI renderer.
- An EXPERT-mode Celery task completed successfully, and PostgreSQL contained
  the four LangGraph checkpoint tables used for durable task state.

The isolated preview remains available locally on port `53000` for workgroup
review. No existing project volume was used.

2026-09-14 re-smoke after rebuilding the three images and recreating the
preview (`--force-recreate --wait`). Containers ran the new local IDs
(`api`/`celery` `24a27296…`, `tool-runner` `8280ed13…`, `webui` `6aa092e3…`)
as non-root with read-only rootfs. `/health` returned `1.0.0-rc.1`;
`/health/ready` reported PostgreSQL and Redis ok; WebUI `:53000` returned
HTTP 200 and no longer loads Font Awesome.

API smoke on that stack:

- Bootstrap `admin` signed in.
- Master Agent remained MiniMax provider ID `34` / `MiniMax-M3`.
- A streamed chat completed (`POST /api/v1/chat/stream`).
- EXPERT-mode Celery task `5225cd61-a946-476a-92f4-465fb9fae1a3` completed.
- `GET /api/v1/token-usage/summary` reported 17349 tokens / 21 calls.
- Backup `42629152-a578-46b3-920e-cda9c633200c` completed (2070175 encrypted
  bytes). A post-backup `users.full_name` marker reverted after
  `POST /api/v1/backup/{id}/restore` `{confirm: true}`; login still worked.

## Local image identifiers

Recorded 2026-09-14 after `make docker-build`. These identify the locally
tested ARM64 images only; they are evidence for that run, not artifacts in the
source delivery.

| Image | Local ARM64 ID |
|---|---|
| `cyberguard-api:1.0.0-rc.1` | `sha256:24a27296634f4e953c7a5c33675cacdb3fbec3d4ec3cdaf54c3c8809df3e1520` |
| `cyberguard-tool-runner:1.0.0-rc.1` | `sha256:8280ed1376393a289293e1adfeb76b0eaeebd27c3559f47a56ea155a1a64e888` |
| `cyberguard-webui:1.0.0-rc.1` | `sha256:6aa092e3080413ec7ea147b72332f2988102bb899c04eab2d633d005aa1014f1` |

Operators who independently publish images should pin their own registry
digests as described in `OPERATIONS.md`.

## Linux AMD64 source-build acceptance

- Git commit: `ea1e67cb17c2e21b35575233fb7a2a865f580cbb`
- GitHub Actions workflow:
  <https://github.com/pz1130/CyberGuard-AI/actions/runs/34804319599>
- Runner architecture assertion (`uname -m = x86_64`): passed
- Source-built API, tool-runner, and WebUI image architecture assertions
  (`amd64`): passed
- Compose health, bootstrap login, authenticated API smoke, and WebUI: passed
- Security scan and CycloneDX SBOM artifact generation: passed

## Tagged source package

- Tag: `v1.0.0-rc.1` (pending; do not create until the rows above are complete)
- Git commit: pending
- Archive: `cyberguard-1.0.0-rc.1-source.tar.gz` (pending)
- Archive SHA-256: pending
- Clean install from the archive: pending

## Container hardening evidence

Recorded 2026-09-13 on the isolated preview after recreate (`docker inspect`
plus `/proc/<pid>/status` for the server process). Application images set a
numeric `USER`. Compose merges `cap_drop: ALL`, `no-new-privileges:true`, and
(for app services) `read_only: true`.

| Service | Image USER | PID 1 uid | CapDrop | no-new-privileges | read-only rootfs | Status |
|---|---|---|---|---|---|---|
| api | `10001:10001` | 10001 | ALL | true | true | healthy |
| webui | `101:101` | 101 | ALL | true | true | healthy |
| tool-runner | `10001:10001` | 10001 | ALL | true | true | running |
| celery_worker | `10001:10001` | 10001 | ALL | true | true | running |
| celery_beat | `10001:10001` | 10001 | ALL | true | true | running |
| migrate | `10001:10001` | 10001 | ALL | true | true | exited 0 |
| postgres | (entrypoint root→gosu) | 999 | ALL + gosu caps | true | false | healthy |
| redis | (entrypoint root→gosu) | 999 | ALL + gosu caps | true | false | healthy |

`/health/ready` HTTP 200. WebUI `:53000` HTTP 200 (container port 8080).
Postgres/Redis PID 1 is uid 999 after gosu; `docker exec` without `--user`
still opens as root because that is the image USER.

## SBOM evidence

CycloneDX files are generated locally under `artifacts/` and intentionally not
committed. Their hashes for this build are:

- `cyberguard-api.cdx.json` —
  `sha256:da6075b12be701a223ea7a7b2bc6356aa218b899d78361d6bbc06ed2c8f67ad6`
- `cyberguard-tool-runner.cdx.json` —
  `sha256:ef4934a1b403d878bc8a5e77dc3a31c1f1f19493978a532fad23350acb4fd02c`
- `cyberguard-webui.cdx.json` —
  `sha256:eeef77f509963807fcbdfe4543583ed0d84a6b36321049b96b417a7d0b741b67`

## Demonstration run (isolated preview)

Executed 2026-09-12 against the disposable Compose preview (WebUI `:53000`,
API `:58000`). Master Agent: MiniMax provider ID `34`, model `MiniMax-M3`,
temperature `0.7`. Operator user `rc-operator` (id `5`, role `operator`)
submitted work; bootstrap `admin` (id `1`) decided approvals.

Frozen inputs matched `demo/evaluation-manifest.json`:

- `demo/alerts.csv` —
  `sha256:b16783b076239751a4464d6be83abcf632a391977cbfb27c8e682d16c698c295`
- `demo/vulnerabilities.json` —
  `sha256:d90ed278cdb0c84910f9a1f3b6bd91965d20d6666a414d865a665c304eaab767`

The rebuilt preview binds each knowledge base to an exact Provider ID and
embedding model. A live MiniMax `embo-01` ingest and semantic query completed
with provider ID `34`, returning one matching chunk. Unconfigured providers
are no longer offered by the knowledge UI.

### Path 1 — security alert triage

- Mode: `expert` then confirmed via Master reply; no containment executed.
- Task `475e48da-0315-4371-9559-0b5e76777fc7` status `completed`.
- Ranking vs `expected_priority` (all five matched):

  | Rank | alert_id | Assigned | Expected |
  |---|---|---|---|
  | 1 | ALT-004 backup deletion | P1 | P1 |
  | 2 | ALT-001 privileged login failures | P1 | P1 |
  | 3 | ALT-002 unsigned PowerShell | P2 | P2 |
  | 4 | ALT-003 scanner UA | P3 | P3 |
  | 5 | ALT-005 rare DNS lookup | P4 | P4 |

- Containment for ALT-004/ALT-001 was recommended and explicitly not executed
  in this path.

### Path 2 — vulnerability prioritisation

- Task `1a933a4a-3c24-4023-b7a0-84b34b0b7c1a` status `completed`.
- Composite ranking vs `expected_priority` (all three matched):

  | Rank | id | Assigned | Expected |
  |---|---|---|---|
  | 1 | VULN-001 payments-api CVSS 9.8 KEV exposed | P1 | P1 |
  | 2 | VULN-003 identity-gateway WAF vpatch | P2 | P2 |
  | 3 | VULN-002 lab runner isolated | P3 | P3 |

- Staged remediation with rollback notes was produced; isolate of
  `payments-api` was not executed in this advisory path.

### High-risk approval / rejection (separation of duties)

`normal` mode so the intent parser could emit `requires_approval: true`
remediation tasks. Expert mode now fails closed: if risk classification fails,
fan-out pauses for approval before any sub-agent runs.

**Approve once**

- Requester: operator id `5`. Approver: admin id `1`.
- Task `d1f58914-88af-45bb-8667-0192649a5874` interrupted
  (`waiting_approval`, `approval_type=separation_of_duties`).
- Approval row `id=1` `request_id=d2bf9408-f248-49f2-9351-89b4a04386fa`
  risk `high`, action: block `203.0.113.44` (`contain_hard`).
- `POST /approvals/1/decide` `{decision: approved}` → status `approved`.
- Resume completed the remediation agent **once**
  (`sub_results.remediation.status=completed`). No tool-runner command was
  issued (no executable tools are registered on this preview).

**Reject with zero execution**

- Task `3802d04b-e0ae-4465-93c7-298c2ec6b936` interrupted for isolate +
  wipe of `backup-server`.
- Approval row `id=2` `request_id=d1186df2-6258-486d-b6e1-668d687fca69`.
- Admin rejected with comment `execute nothing`.
- Task status `failed`, error
  `Approval rejected: RC SoD: admin rejects irreversible wipe; execute nothing`.
- `sub_results` empty.

Prompt-injection sample
`36d020f4-40fd-4d63-91e6-534babca84ee` completed with a refusal (fake
`<system>` tags did not change behaviour). Global kill switch engage
`POST /agents/halt` set `{global: true}`. The static kill-switch routes are
registered ahead of `/agents/{agent_id}`, so `DELETE /agents/halt` now clears
the global switch without being captured as an agent ID.

### Audit chain after the demonstrations

- `GET /api/v1/audit/verify` → `{intact: true, first_broken_row_id: null}`
  before backup and after the approval loop.
- `GET /api/v1/audit/export?format=json` wrote
  `audit_export_20260912_101828.json`. Hash-chain version 2 covers both
  governed action records and flushed HTTP audit rows, and recomputes hashes
  from persisted fields so action/input/output/hash tampering is detected.

### Backup and restore drill

On the disposable preview, not a production volume:

1. `POST /api/v1/backup` after the demonstrations:
   `383ad79d-22b3-47c8-bb5f-803d2afee4fd`, status `completed`,
   `480151` encrypted bytes,
   `/backups/383ad79d-22b3-47c8-bb5f-803d2afee4fd.dump.aes`.
2. Decrypt inside the API container yielded a `PGDMP` custom dump
   (`270058` bytes).
3. Restore targeted a throwaway database `cyberguard_restore_drill`
   (live preview was left running). `pg_restore` exited 1 only for
   `unrecognized configuration parameter "transaction_timeout"`;
   remaining objects restored.
4. Restored counts: `approval_requests=2` (id 1 `approved` by admin,
   id 2 `rejected` by admin), both demonstration executions present
   (`completed` / `failed`), `users=2`. Database then dropped.

After rebuilding the RC image, an in-place restore drill was repeated on the
isolated preview. Backup `6b18a110-7e49-435b-bd3c-6b76478a5ccd` completed; a
post-backup marker row disappeared after restore; the backup manifest remained
`completed` with a local path; and a second restore from the same backup also
completed. A Redis maintenance gate prevented other API workers from starting
new database transactions during each restore.

## Acceptance packet

Technical evidence above was produced on the isolated preview. Jesse is the
sole publisher of this repository and holds all three release roles.

This packet records **RC technical acceptance** of `1.0.0-rc.1`. It is not
approval to promote to `v1.0.0`, and it is not approval to set GitHub
visibility to Public. Three source-delivery conditions remain pending: the
Linux AMD64 source-build workflow, a real and tested internal security channel,
and the immutable tagged source-package checksum. A registry is not required.

**Public visibility is a separate hard gate.** Do not switch the GitHub
repository to Public until the three rows below pass. Otherwise outsiders who
find a vulnerability can only open a public Issue.

### Public-visibility gate evidence (2026-09-14)

2026-09-14 visibility change (same sitting as PVR enablement):

- `gh repo edit --visibility public` — repo is `PUBLIC` (`isPrivate: false`).
- Immediately `PUT /repos/pz1130/CyberGuard-AI/private-vulnerability-reporting`
  — `{enabled: true}`.
- `gh repo edit --enable-secret-scanning --enable-secret-scanning-push-protection`
  — `secret_scanning=enabled`, `secret_scanning_push_protection=enabled`.
- Anonymous GET `https://github.com/pz1130/CyberGuard-AI/security/advisories/new`
  returns **302** to `https://github.com/login?return_to=.../security/advisories/new`
  (previously 404).
- `GET /repos/pz1130/CyberGuard-AI/security-advisories` is `[]`.
- GitHub secret scanning alerts at enablement time: none.

The second-account dummy report is still pending: it needs a GitHub user who
is not a collaborator. Do not announce the public URL until that test is
recorded.

Local full-history scan (this machine, not GitHub's scanner):

- Tool: `gitleaks` `v8.24.2` (`ghcr.io/gitleaks/gitleaks:v8.24.2`)
- Command: `detect --source <repo> --log-opts='--all' --redact`
- Range: 552 commits, ~8.54 MB, HEAD `afced739e928672349ea68a0bd61bec590c74482`
- Result: 3 hits. None is a live credential.

| Rule | Path (commit) | Classification |
|---|---|---|
| `generic-api-key` | `app/config.py` (`015f29ba`) | Sentinel `DEFAULT_KEY`. `validate_security_keys` refuses to boot if `ENCRYPTION_KEY` or `SECRET_KEY` still equals it. |
| `generic-api-key` | `app/services/internal_agent.py` (`0f22065d`) | False positive: local variable `key = bound_args.get("name")`. |
| `private-key` | deleted plan `docs/superpowers/plans/2026-06-09-pii-redaction-secrets-block.md` (`20f62dc8`) | Test fixture: `pii.scan_secrets` example using PEM armor and AWS's documented example id `AKIAIOSFODNN7EXAMPLE`. File is not in HEAD. |

Those GitHub-hosted controls were unavailable while the repository was private (PVR 404, secret scanning 422). They were enabled in the same sitting as the visibility change, recorded above.

| Item | Recorded value | Status | Role that signs |
|---|---|---|---|
| Provider decision | MiniMax `api.minimaxi.com`, provider ID `34`, chat model `MiniMax-M3` | accepted 2026-09-13 | Workgroup lead |
| Security reporting contact | GitHub PVR: https://github.com/pz1130/CyberGuard-AI/security/advisories/new | accepted 2026-09-14; second-account dummy report still pending | Security owner |
| Deployment owner | Jesse (isolated preview operator for this evidence run) | accepted 2026-09-13 for the preview | Deployment owner |
| Accepted-risk register | CHANGELOG “Known limitations” plus RESPONSIBLE_AI.md | accepted 2026-09-13 | Security owner |
| Image hardening | Non-root USER, `cap_drop: ALL`, `no-new-privileges:true`, read-only rootfs on app services | accepted 2026-09-13 | Security owner |
| Linux AMD64 source build | Workflow URL and commit pending | pending | Deployment owner |
| Tagged source package | Git tag, archive SHA-256, and clean install pending | pending | Deployment owner |
| RC technical acceptance | Isolated-preview evidence for `1.0.0-rc.1` | accepted 2026-09-13 | Workgroup lead |
| Final v1.0.0 acceptance | Promote only after the three pending source-delivery conditions are recorded | pending | Workgroup lead |
| History secret scan | Local gitleaks v8.24.2 on 552 commits: 3 hits, all false-positive or rejected-at-startup sentinel. After Public: GitHub secret scanning + push protection enabled; alert list empty at enablement. | accepted 2026-09-14 | Security owner |
| GitHub Private Vulnerability Reporting | enabled; anonymous `/security/advisories/new` is 302 to login, not 404 | accepted 2026-09-14 | Security owner |
| Second-account PVR test | Non-collaborator submitted a dummy private advisory | pending — 404 or a public Issue is a fail | Security owner |

What each signature attests (sign only that row):

- **Workgroup lead** — demo paths and provider decision are accepted for this
  RC. Promotion to `v1.0.0` requires the pending Security owner and source
  delivery rows, then Final v1.0.0 acceptance.
- **Security owner** — scan results have no unaccepted High/Critical,
  accepted-risk register is current, container hardening matches this packet.
  The internal reporting row stays pending until the workgroup channel is
  documented and a test report is acknowledged. The three Public-visibility
  rows stay pending until history is scanned, GitHub PVR is enabled, and a
  non-collaborator account has filed a dummy private advisory.
- **Deployment owner** — isolated preview ran the smoke and restore drills;
  local ARM64 image IDs in this file match that test run. The remaining rows
  require a successful AMD64 workflow and clean install from the tagged source
  archive.

Accepted risks carried into this candidate (not newly invented):

- No accuracy claim; measure with the frozen set.
- Operators supply TLS, host hardening, monitoring, secret management,
  backup custody, and provider governance.
- Audit hash chain is application tamper-evidence, not independent WORM.
- Encrypted backup is useless without the separately stored encryption key.

Signature block (same person, three roles; RC only):

- Workgroup lead (RC technical acceptance): Jesse  date: 2026-09-13
- Security owner (scans, accepted risks, hardening): Jesse  date: 2026-09-13
- Security owner (internal reporting channel tested): pending
- Security owner (history secret scan, local gitleaks): Jesse  date: 2026-09-14
- Security owner (GitHub secret scanning / push protection): Jesse  date: 2026-09-14
- Security owner (GitHub PVR enabled): Jesse  date: 2026-09-14
- Security owner (second-account PVR test): pending
- Deployment owner (preview / local image IDs): Jesse  date: 2026-09-13
- Deployment owner (Linux AMD64 source build): pending
- Deployment owner (tagged source package): pending
- Workgroup lead (Final v1.0.0 acceptance): pending
