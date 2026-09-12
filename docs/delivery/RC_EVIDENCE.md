# RC Verification Evidence

Candidate: `1.0.0-rc.1`  
Branch: `codex/release-candidate`  
Verification date: 2026-09-12 (Asia/Shanghai)

## Automated gate

- `make check`: 540 passed, 1 skipped; frontend type check and lint ratchet
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
- The Master Agent persisted `MiniMax` Provider ID `34` together with the exact
  verified model name `MiniMax-M3`; a cross-provider model save returned 400.
- A live streamed chat completed through that Master Agent selection, including
  provider reasoning tags handled by the collapsed WebUI renderer.
- An EXPERT-mode Celery task completed successfully, and PostgreSQL contained
  the four LangGraph checkpoint tables used for durable task state.

The isolated preview remains available locally on port `53000` for workgroup
review. No existing project volume was used.

## Local image identifiers

- `cyberguard-api:1.0.0-rc.1` —
  `sha256:de49726c09d3b6bbcac421a3e9c93cd64f914da96d05ad7e0151f4b52fbf9f61`
- `cyberguard-tool-runner:1.0.0-rc.1` —
  `sha256:8c35edddac625ee8c8ba96f74d2d8d572403920af9489413714d91a5636d8ce6`
- `cyberguard-webui:1.0.0-rc.1` —
  `sha256:5c63b072ad2afa67a57d5ed08eb6cc79123110831a61bcdc30b9dad7a126b0f7`

These are local image identifiers, not registry digests. Record immutable
registry digests after publishing.

## SBOM evidence

CycloneDX files are generated locally under `artifacts/` and intentionally not
committed. Their hashes for this build are:

- `cyberguard-api.cdx.json` —
  `sha256:0a6f69deb85da5bdfb0978c92239353098320607b2d0c4c0416aa2af85ba282d`
- `cyberguard-tool-runner.cdx.json` —
  `sha256:bfc6989ebb399cafc7865dd892c61602b6131403d6b821c83e4d8154a112c562`
- `cyberguard-webui.cdx.json` —
  `sha256:5bad73a13f58dc889b19dc1ac0a049a862c2adc4c0bd57e206c91767f76bd62e`

## Still requiring workgroup evidence

- Two model-backed demonstration paths and their measured outputs.
- Human approval/rejection demonstration with separation of duties.
- Audit-chain verification after those demonstrations.
- Backup and restore drill using disposable demonstration data.
- Deployment-specific owner, security-reporting contact, provider decision,
  accepted-risk register, and final acceptance signatures.
