# RC Verification Evidence

Candidate: `1.0.0-rc.1`  
Branch: `codex/release-candidate`  
Verification date: 2026-09-12 (Asia/Shanghai)

## Automated gate

- `make check`: 539 passed, 1 skipped; frontend type check and lint ratchet
  passed; production npm audit reported 0 vulnerabilities.
- Fresh Alembic migration: `032_agent_run_events (head)`, with one head.
- Compose configuration validation: passed with explicit non-default secrets.
- Release image build: API, tool-runner, and WebUI built successfully.
- Container scan: no known, fixed Critical finding in the three release images.

## Runtime smoke test

An isolated Compose project with separate ports and disposable volumes was
started with `docker compose up -d --wait`. PostgreSQL, Redis, API, tool-runner,
Celery worker, Celery beat, and WebUI reached their expected running/healthy
states. The following checks passed:

- `/health` returned version `1.0.0-rc.1`.
- `/health/ready` reported PostgreSQL and Redis healthy.
- The explicitly configured bootstrap administrator could sign in.
- The OpenAPI surface contained 116 paths and no Group Chat, Schedule, N8N, or
  Webhook route.
- The WebUI root returned HTTP 200.

The isolated project and all of its disposable volumes were removed after the
test. No existing project volume was used.

## Local image identifiers

- `cyberguard-api:1.0.0-rc.1` —
  `sha256:8bf01323e0b78a6b066f3b59005f2314454e7400715f21ab549dcd010774d9cc`
- `cyberguard-tool-runner:1.0.0-rc.1` —
  `sha256:8c35edddac625ee8c8ba96f74d2d8d572403920af9489413714d91a5636d8ce6`
- `cyberguard-webui:1.0.0-rc.1` —
  `sha256:c40f823d1a5608f4e40635fc5e36238e075428174db528b324faaa36c05e676f`

These are local image identifiers, not registry digests. Record immutable
registry digests after publishing.

## SBOM evidence

CycloneDX files are generated locally under `artifacts/` and intentionally not
committed. Their hashes for this build are:

- `cyberguard-api.cdx.json` —
  `sha256:9fa0afa6cd0e3ffb09827922d51bcc42ddc2b6335bb5619b17e3244ee902cb1e`
- `cyberguard-tool-runner.cdx.json` —
  `sha256:5edf1dea6fe219e58cf562d1b3f9741fc6a1110c72068d78a31f9e42b4713976`
- `cyberguard-webui.cdx.json` —
  `sha256:1e72614c68a7f7da2e91158c128e4030cd4ff48c2907c8315aac43d7140484cc`

## Still requiring workgroup evidence

- Three model-backed demonstration paths and their measured outputs.
- Human approval/rejection demonstration with separation of duties.
- Audit-chain verification after those demonstrations.
- Backup and restore drill using disposable demonstration data.
- Deployment-specific owner, security-reporting contact, provider decision,
  accepted-risk register, and final acceptance signatures.
