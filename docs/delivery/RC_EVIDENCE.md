# RC Verification Evidence

Candidate: `1.0.0-rc.1`  
Branch: `codex/release-candidate`  
Verification date: 2026-09-12 (Asia/Shanghai)

## Automated gate

- `make check`: 534 passed, 1 skipped; frontend type check and lint ratchet
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
  `sha256:3f6f46a8a29920a35889bf0a16e7e1c82030ab33bb682bdbf557931f0f0b918b`
- `cyberguard-tool-runner:1.0.0-rc.1` —
  `sha256:8c35edddac625ee8c8ba96f74d2d8d572403920af9489413714d91a5636d8ce6`
- `cyberguard-webui:1.0.0-rc.1` —
  `sha256:1fd828ee8fa3a38ae49d6bcbda219df30a0cd4243e93fe8574f72c7c6cf106d7`

These are local image identifiers, not registry digests. Record immutable
registry digests after publishing.

## SBOM evidence

CycloneDX files are generated locally under `artifacts/` and intentionally not
committed. Their hashes for this build are:

- `cyberguard-api.cdx.json` —
  `sha256:124c1c99e4d7329e3306daa435a359127652ad1828e52f1b97659433d6aab91b`
- `cyberguard-tool-runner.cdx.json` —
  `sha256:464b4bb52ea95a53dc48f57a390c5e7e154a67e5ba84fe2459c53f9db1a898ff`
- `cyberguard-webui.cdx.json` —
  `sha256:33ad594a3bd9022199905e4c086363675b74a169ca63f5eba31ba4c4380a2113`

## Still requiring workgroup evidence

- Two model-backed demonstration paths and their measured outputs.
- Human approval/rejection demonstration with separation of duties.
- Audit-chain verification after those demonstrations.
- Backup and restore drill using disposable demonstration data.
- Deployment-specific owner, security-reporting contact, provider decision,
  accepted-risk register, and final acceptance signatures.
