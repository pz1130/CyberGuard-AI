# RC Verification Evidence

Candidate: `1.0.0-rc.1`  
Branch: `codex/release-candidate`  
Verification date: 2026-09-12 (Asia/Shanghai)

## Automated gate

- `make check`: 528 passed, 1 skipped; frontend type check and lint ratchet
  passed; production npm audit reported 0 vulnerabilities.
- Fresh Alembic migration: `034_focus_security_operations (head)`, with one head.
- Compose configuration validation: passed with explicit non-default secrets.
- Release image build: API, tool-runner, and WebUI built successfully.
- Container scan: no known, fixed Critical finding in the three release images.

## Runtime smoke test

An isolated Compose preview with separate ports was started with
`docker compose up -d --wait`. PostgreSQL, Redis, API, tool-runner, Celery
worker, Celery beat, and WebUI reached their expected running/healthy states.
The following checks passed:

- `/health` returned version `1.0.0-rc.1`.
- `/health/ready` reported PostgreSQL and Redis healthy.
- The explicitly configured bootstrap administrator could sign in.
- The OpenAPI surface contains no GRC Assessment, Group Chat, Schedule, N8N,
  or Webhook route.
- The WebUI root returned HTTP 200.

The isolated preview remains available locally on port `53000` for workgroup
review. No existing project volume was used.

## Local image identifiers

- `cyberguard-api:1.0.0-rc.1` —
  `sha256:76cbfcd59fe4676688879e2d1ee6aed7df6642fedfa30d59000581018d9e57d6`
- `cyberguard-tool-runner:1.0.0-rc.1` —
  `sha256:8c35edddac625ee8c8ba96f74d2d8d572403920af9489413714d91a5636d8ce6`
- `cyberguard-webui:1.0.0-rc.1` —
  `sha256:79b9c3a524459f35199966c8e73b873c8293c3f4e44d4558002073b8a0d08eb5`

These are local image identifiers, not registry digests. Record immutable
registry digests after publishing.

## SBOM evidence

CycloneDX files are generated locally under `artifacts/` and intentionally not
committed. Their hashes for this build are:

- `cyberguard-api.cdx.json` —
  `sha256:9fa25c21013c285926c2df26cbe8dad48fbd19132578adbe3ef143db1acd0a6d`
- `cyberguard-tool-runner.cdx.json` —
  `sha256:00f04c500924cefa9471a76a8fbf48e66808452526d56a37dd12445b305fa75d`
- `cyberguard-webui.cdx.json` —
  `sha256:fcc42a70e70dec33e49b27c9e448a77d81189f7a70d66fbbe2faeb3f47726191`

## Still requiring workgroup evidence

- Two model-backed demonstration paths and their measured outputs.
- Human approval/rejection demonstration with separation of duties.
- Audit-chain verification after those demonstrations.
- Backup and restore drill using disposable demonstration data.
- Deployment-specific owner, security-reporting contact, provider decision,
  accepted-risk register, and final acceptance signatures.
