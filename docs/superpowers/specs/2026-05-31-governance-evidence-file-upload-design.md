# Governance Evidence File Upload (`kind=file`) — Design

**Date:** 2026-05-31
**Status:** Approved — proceeding to implementation plan

## Background

The `Evidence` model (`gov_evidences`) and schemas already declare a `file` kind
(`EvidenceKind = Literal["file", "url", "text"]`) plus the columns `file_path`,
`mime_type`, `size_bytes`, `uploaded_by_user_id`. But the create path only handles
`url`/`text`: `POST /governance/req-assessments/{ra_id}/evidence` takes a JSON
`EvidenceCreate` body, and the frontend form state is narrowed to `'text' | 'url'`.
So `kind=file` is dead — no way to upload, store, or download a file. This design
wires it up on both ends.

**No DB migration is needed** — all required columns already exist.

## Goal

A user can attach a file as evidence for a requirement assessment: upload it through
the Governance UI, see it listed, download it, and delete it (which also removes the
stored file). Files are validated (type + size + magic-byte) and stored on a local
volume, consistent with the project's existing backup-storage pattern.

## Non-goals

- S3/OSS storage for evidence (local dir only; S3 can be layered later, like backup).
- Multiple files per evidence row (one `Evidence` row = one file, matching the single
  `file_path` column).
- Virus scanning, thumbnailing, or preview rendering.

## Architecture decisions (with rejected alternatives)

1. **Separate multipart endpoint** for file upload; the existing JSON endpoint for
   `url`/`text` is untouched.
   - *Rejected:* overloading `add_evidence` to always be multipart — breaks the JSON
     contract for url/text and adds needless churn.
2. **Authenticated download** endpoint. Evidence may be sensitive, so the download
   requires auth; the frontend fetches with the Bearer token → blob → triggers a save.
   A plain `<a href>` cannot send the token.
   - *Rejected:* signed/temporary URL tokens — overkill for a single-node app.
3. **Shared upload validator.** Extract chat's inlined validation into
   `app/core/uploads.py` and reuse it, rather than duplicating the magic-byte table.

## Storage

- Directory: `EVIDENCE_DIR = os.environ.get("CYBERGUARD_EVIDENCE_DIR", "/data/evidence")`,
  created with `os.makedirs(EVIDENCE_DIR, exist_ok=True)` — same pattern as
  `CYBERGUARD_BACKUP_DIR` in `app/routers/backup.py`.
- On-disk filename: `uuid4().hex` (no extension needed; mime is stored in DB). This
  prevents collisions and path-traversal via user-supplied names. The original
  filename is preserved in `Evidence.name`.
- `Evidence.file_path` stores the path **relative to `EVIDENCE_DIR`** (just the uuid
  filename), so the directory can be relocated without rewriting rows.
- `docker-compose.yml`: add a named volume `evidence_data:/data/evidence` to the `api`
  service and to the top-level `volumes:` section.

## Components

### Backend

1. **`app/core/uploads.py`** (new) — shared upload validation:
   - `ALLOWED_ATTACHMENT_TYPES: set[str]` and `MAX_FILE_SIZE` (moved from `chat.py`).
   - `_MAGIC_BYTES` map (moved from `chat.py`).
   - `async def validate_and_read_upload(file: UploadFile) -> tuple[bytes, str]` —
     validates content-type is allowed, size ≤ `MAX_FILE_SIZE` (both the declared
     `file.size` and the actual read length), and the leading bytes match the
     declared type's magic signature (where one is defined). Returns `(content, mime)`
     or raises `HTTPException(400, ...)`.
   - `app/routers/chat.py` is refactored to import these instead of its inline copies
     (behavior unchanged; existing chat tests guard parity).

2. **`POST /governance/req-assessments/{ra_id}/evidence/file`** (in
   `app/routers/governance.py`):
   - Params: `file: UploadFile = File(...)`, `name: str = Form(...)`,
     `description: str | None = Form(None)`.
   - Permission: `SETTINGS_WRITE` (same as existing `add_evidence`).
   - Flow: 404 if `ra_id` missing → `validate_and_read_upload(file)` →
     `os.makedirs(EVIDENCE_DIR, exist_ok=True)` → `fname = uuid4().hex` → write bytes
     to `EVIDENCE_DIR/<fname>` (no extension; mime lives in DB) → create
     `Evidence(kind="file", file_path=fname, mime_type=<mime>, size_bytes=len(content),
     name=name, description=description, uploaded_by_user_id=current_user.user_id)` →
     commit → return `EvidenceRead`.

3. **`GET /governance/evidence/{ev_id}/download`** (in `app/routers/governance.py`):
   - Permission: `SETTINGS_READ`.
   - Flow: 404 if evidence missing or `kind != "file"`; resolve `EVIDENCE_DIR/file_path`,
     verify the resolved path stays within `EVIDENCE_DIR` (path-traversal guard),
     404 if the file is missing on disk; return `FileResponse(path, media_type=mime_type,
     filename=name)`.

4. **`delete_evidence` change** (`DELETE /governance/evidence/{ev_id}`):
   - When `kind == "file"` and `file_path` set: resolve under `EVIDENCE_DIR`, verify
     containment, then best-effort `os.remove` (swallow `FileNotFoundError`). Then
     delete the DB row as today.

### Frontend (`webui/src/pages/Governance.tsx`, `webui/src/api/client.ts`)

5. `newEvidence` state `kind` widened to `'text' | 'url' | 'file'`; add
   `file: File | null`. Kind selector gains `<option value="file">FILE</option>`.
   When `kind === 'file'`, render `<input type="file">` (sets `newEvidence.file`).
6. `addEvidence`: when `kind === 'file'`, require a chosen file and call
   `api.uploadEvidenceFile(raId, file, name)`; otherwise the existing JSON path.
7. Evidence row: when `ev.kind === 'file'`, render a **download button** (calls
   `api.downloadEvidence(ev.id)`) plus the human-readable size (`ev.size_bytes`).
8. `client.ts`:
   - `uploadEvidenceFile(raId, file, name, description?)` — builds `FormData`, POSTs
     multipart with the Bearer header (no `Content-Type` header — the browser sets the
     multipart boundary).
   - `downloadEvidence(id)` — `fetch` with Bearer token, read `blob()`, create an
     object URL, trigger an `<a download>` click, revoke the URL.

## Error handling

| Condition | Response |
|-----------|----------|
| Disallowed type / magic-byte mismatch | `400` |
| File exceeds `MAX_FILE_SIZE` | `400` |
| `ra_id` not found (upload) | `404` |
| Evidence not found / not `kind=file` (download) | `404` |
| File missing on disk (download) | `404` with clear message |
| Resolved path escapes `EVIDENCE_DIR` | `404` (treated as not found) |

## Testing (TDD, backend-focused)

Tests live in `tests/test_evidence_file.py` (new). They `monkeypatch` the governance
router's `EVIDENCE_DIR` to a `tmp_path` and reuse the existing DB-backed fixture
pattern (require the 5433 postgres). The router functions are called directly with a
fake authenticated user, mirroring `tests/test_agent_stream_endpoint.py` /
`tests/test_ocr_endpoint.py`.

- Upload a valid file → creates the on-disk file (`EVIDENCE_DIR/<file_path>` exists)
  and an `Evidence` row with `kind="file"`, correct `mime_type`/`size_bytes`, and a
  `file_path` that is the bare relative filename (no directory separators).
- Upload with a magic-byte mismatch (e.g. a `.png` content-type but non-PNG bytes) →
  `HTTPException(400)`, no row, no file.
- Upload exceeding `MAX_FILE_SIZE` → `400`.
- Download returns the exact stored bytes with the original filename.
- Delete an evidence of `kind=file` removes both the DB row and the on-disk file.
- `app/core/uploads.validate_and_read_upload` unit test for allow/reject paths.

Existing chat attachment tests (if any) must still pass after the `uploads.py`
extraction — parity guard for the refactor.

## Files touched

- `app/core/uploads.py` (new)
- `app/routers/chat.py` (modify — import shared validator)
- `app/routers/governance.py` (modify — upload + download endpoints, delete change,
  `EVIDENCE_DIR`)
- `docker-compose.yml` (modify — `evidence_data` volume)
- `webui/src/api/client.ts` (modify — `uploadEvidenceFile`, `downloadEvidence`)
- `webui/src/pages/Governance.tsx` (modify — file kind in form + download in row)
- `tests/test_evidence_file.py` (new)
- `docs/superpowers/plans/project_status.md` (modify — move evidence-file out of the
  "Not yet implemented" list once done)
