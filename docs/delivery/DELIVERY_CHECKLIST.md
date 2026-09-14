# IFI Source Delivery Checklist

CyberGuard is delivered as source for local Docker builds. No desktop client,
prebuilt container image, registry account, or provider credential is part of
the package.

## Package contents

- Source archive created from the immutable `v1.0.0-rc.1` tag
- SHA-256 checksum and provenance manifest for that archive
- `README.md`, `.env.example`, Dockerfiles, and `docker-compose.yml`
- Operations, architecture/security, responsible-AI, demo, and evaluation docs
- `SECURITY.md` containing the approved internal reporting channel
- MIT `LICENSE`, `uv.lock`, and `webui/package-lock.json`
- CycloneDX SBOMs, High/Critical container scan results, and RC evidence

The lockfiles are the exact application dependency inventories. The SBOMs add
resolved operating-system packages and detected license metadata for the built
images. Reviewers should assess both; neither is a legal opinion.

## Acceptance platform

- Linux AMD64 (`x86_64`)
- Docker Engine with Docker Compose v2
- Outbound network access to configured model providers only as allowed by the
  operator's policy
- TLS, host hardening, monitoring, secrets, backup custody, and retention
  supplied by the operator

The GitHub release gate must show an AMD64 source build, healthy Compose stack,
successful bootstrap-admin login, authenticated API smoke tests, and a working
WebUI. Live model conversation remains a manual test because CI receives no
provider credential.

## Release procedure

1. Run `make rc-check` and retain its results and SBOMs.
2. Record the successful AMD64 workflow URL and commit in `RC_EVIDENCE.md`.
3. Replace the pending security-channel marker in `SECURITY.md`; send and
   acknowledge a test report.
4. Commit the final documents and confirm `git status --short` is empty.
5. Create the annotated `v1.0.0-rc.1` tag. Never move or reuse it.
6. Run `make source-package VERSION=1.0.0-rc.1 REF=v1.0.0-rc.1`.
7. Copy the archive SHA-256 and Git commit into `RC_EVIDENCE.md`.
8. Verify the checksum and perform one final install from the archive.

## Operator first start

1. Copy `.env.example` to `.env` and replace every placeholder secret.
2. Run `docker compose config --quiet`, `docker compose build`, then
   `docker compose up -d`.
3. Confirm `/health/ready` and the WebUI respond.
4. Sign in with the one-time `BOOTSTRAP_ADMIN_USERNAME` and
   `BOOTSTRAP_ADMIN_PASSWORD`; rotate that password after first login.
5. Configure and test an approved Provider, then bind the Master Agent to that
   Provider ID and one of its verified model names.
6. Exercise chat, token usage, EXPERT task mode, approval, backup, and restore
   before admitting real data.

Upgrade, backup/restore, incident response, and irreversible volume deletion
are covered in `OPERATIONS.md`. Never ship a populated `.env`, fixed shared
administrator password, provider key, database volume, or backup file.
