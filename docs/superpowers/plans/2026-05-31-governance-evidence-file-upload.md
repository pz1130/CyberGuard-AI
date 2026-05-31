# Governance Evidence File Upload (`kind=file`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user attach, download, and delete a file as compliance evidence on a requirement assessment — wiring the already-declared `kind="file"` end-to-end (multipart upload → local-dir storage → authenticated download → delete-removes-file), plus the Governance UI form.

**Architecture:** A new multipart endpoint stores validated bytes to a local directory (`CYBERGUARD_EVIDENCE_DIR`, like the existing backup dir) under a UUID filename and records `kind="file"` + `file_path`/`mime_type`/`size_bytes` on the existing `Evidence` row. A separate authenticated endpoint serves the file. The existing JSON `add_evidence` (url/text) is untouched. Chat's inline upload validation is extracted to a shared `app/core/uploads.py` and reused.

**Tech Stack:** FastAPI (`UploadFile`/`Form`/`FileResponse`), SQLAlchemy async, pytest/pytest-asyncio, React + TypeScript (`FormData` + blob download), Docker Compose volume.

**Design spec:** `docs/superpowers/specs/2026-05-31-governance-evidence-file-upload-design.md`

**No DB migration needed** — `gov_evidences` already has `file_path`, `mime_type`, `size_bytes`, `uploaded_by_user_id`.

**Run tests with the project venv against the 5433 postgres** (`python` is not on PATH; 5432 is another project's DB):
`DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest`
Bring the stack up first: `docker compose up -d postgres redis` (redis may already be running on 6379 from another project — that's fine for these tests, which only need postgres).

---

## File Structure

- `app/core/uploads.py` (create) — shared upload validation: allowed types, size cap, magic-byte map, `validate_and_read_upload()`.
- `app/routers/chat.py` (modify) — import the shared validator instead of inline copies.
- `app/routers/governance.py` (modify) — `EVIDENCE_DIR`; `POST .../evidence/file`; `GET /governance/evidence/{id}/download`; delete-removes-file.
- `docker-compose.yml` (modify) — `evidence_data` named volume on the `api` service.
- `webui/src/api/client.ts` (modify) — `uploadEvidenceFile`, `downloadEvidence`.
- `webui/src/pages/Governance.tsx` (modify) — `file` kind in the add form + download button + size in the evidence row; widen `Evidence` interface.
- `tests/test_evidence_file.py` (create) — endpoint + validator tests.

---

## Task 1: Extract shared upload validator (`app/core/uploads.py`) and reuse it in chat

This is a parity refactor of chat's validation plus a new reusable module. There are no dedicated chat-attachment tests, so parity is guarded by (a) the full suite still importing/passing and (b) a new unit test for the extracted validator.

**Files:**
- Create: `app/core/uploads.py`
- Modify: `app/routers/chat.py`
- Test: `tests/test_evidence_file.py` (validator unit tests — created here, grown in later tasks)

- [ ] **Step 1: Create `app/core/uploads.py`**

```python
"""Shared validation for multipart file uploads.

Single source of truth for allowed MIME types, the per-file size cap, and
magic-byte anti-spoofing. Used by chat attachments and governance evidence
file uploads so the rules can't drift apart.
"""
from fastapi import HTTPException, UploadFile, status

ALLOWED_ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file

# Magic byte signatures for spoofing detection (claimed type must match content).
_MAGIC_BYTES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/gif": b"GIF8",
    "image/webp": b"RIFF",
    "application/pdf": b"%PDF",
    "application/msword": b"\xd0\xcf\x11\xe0",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK",
    "application/vnd.ms-excel": b"\xd0\xcf\x11\xe0",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK",
    "application/vnd.ms-powerpoint": b"\xd0\xcf\x11\xe0",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": b"PK",
}


async def validate_and_read_upload(file: UploadFile) -> tuple[bytes, str]:
    """Validate an UploadFile's type/size/magic-bytes; return (content, mime).

    Raises HTTPException(400) on any violation. Mirrors the checks previously
    inlined in the chat-attachments endpoint.
    """
    if file.content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Allowed: {', '.join(sorted(ALLOWED_ATTACHMENT_TYPES))}",
        )
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{file.filename}' exceeds maximum size of "
                   f"{MAX_FILE_SIZE // (1024 * 1024)} MB",
        )
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{file.filename}' exceeds maximum size of "
                   f"{MAX_FILE_SIZE // (1024 * 1024)} MB",
        )
    if file.content_type in _MAGIC_BYTES and len(content) >= 8:
        expected = _MAGIC_BYTES[file.content_type]
        if not content[:len(expected)].startswith(expected):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' content does not match declared "
                       f"type '{file.content_type}'",
            )
    return content, file.content_type
```

- [ ] **Step 2: Write the validator unit tests (create `tests/test_evidence_file.py`)**

```python
import io
import os
import uuid

import pytest
import pytest_asyncio
from types import SimpleNamespace
from starlette.datastructures import Headers, UploadFile


def _upload(content: bytes, filename: str, ctype: str) -> UploadFile:
    """Build a Starlette UploadFile for direct endpoint/validator calls."""
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": ctype}),
    )


# A minimal valid-looking PDF (magic %PDF, >= 8 bytes).
GOOD_PDF = b"%PDF-1.4\n%fake pdf body\n"


@pytest.mark.asyncio
async def test_validate_accepts_good_pdf():
    from app.core.uploads import validate_and_read_upload
    content, mime = await validate_and_read_upload(_upload(GOOD_PDF, "a.pdf", "application/pdf"))
    assert content == GOOD_PDF
    assert mime == "application/pdf"


@pytest.mark.asyncio
async def test_validate_rejects_unknown_type():
    from fastapi import HTTPException
    from app.core.uploads import validate_and_read_upload
    with pytest.raises(HTTPException) as ei:
        await validate_and_read_upload(_upload(b"xxxxxxxx", "a.exe", "application/x-msdownload"))
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_rejects_magic_mismatch():
    from fastapi import HTTPException
    from app.core.uploads import validate_and_read_upload
    # Claims PNG but bytes aren't a PNG.
    with pytest.raises(HTTPException) as ei:
        await validate_and_read_upload(_upload(b"not-a-png-at-all", "a.png", "image/png"))
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_rejects_oversize(monkeypatch):
    from fastapi import HTTPException
    import app.core.uploads as up
    monkeypatch.setattr(up, "MAX_FILE_SIZE", 4)
    with pytest.raises(HTTPException) as ei:
        await up.validate_and_read_upload(_upload(b"text/plain body well over four", "a.txt", "text/plain"))
    assert ei.value.status_code == 400
```

- [ ] **Step 3: Run the validator tests — expect PASS**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -v`
Expected: 4 passed. (No DB used yet.)

- [ ] **Step 4: Refactor `app/routers/chat.py` to use the shared validator**

In `app/routers/chat.py`, delete the module-level `ALLOWED_ATTACHMENT_TYPES = {...}` block (lines ~88–105) and `MAX_FILE_SIZE = 10 * 1024 * 1024` (line ~106), and delete the inline `_MAGIC_BYTES = {...}` dict inside `chat_attachments` (lines ~146–155). Add this import near the other `app.core` imports at the top of the file:

```python
from app.core.uploads import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_FILE_SIZE,
    validate_and_read_upload,
)
```

Then replace the per-file validation+read loop body (the block starting `if f.content_type not in ALLOWED_ATTACHMENT_TYPES:` through the magic-byte check, ending right before `attachments.append(`) with a single call:

```python
        content, _mime = await validate_and_read_upload(f)
```

Leave the `if len(files) > 10:` guard and the `attachments.append({...})` (which base64-encodes `content`) exactly as they were. `ALLOWED_ATTACHMENT_TYPES` / `MAX_FILE_SIZE` remain imported because the endpoint docstring/other references may use them; if after editing they are unused, leave the import of `validate_and_read_upload` only and drop the two names. Verify by reading the final function.

- [ ] **Step 5: Verify chat still imports and the suite is green**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -c "import app.routers.chat; print('chat import ok')"`
Expected: `chat import ok` (no ImportError / NameError).

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest -q`
Expected: same pass count as before this plan plus the 4 new validator tests; the 3 known `test_integration.py::TestMasterAgentStateMachine` redis failures are environmental and unrelated.

- [ ] **Step 6: Commit**

```bash
git add app/core/uploads.py app/routers/chat.py tests/test_evidence_file.py
git commit -m "refactor(uploads): extract shared validate_and_read_upload; chat reuses it"
```

---

## Task 2: Upload endpoint `POST /governance/req-assessments/{ra_id}/evidence/file`

**Files:**
- Modify: `app/routers/governance.py` (imports; `EVIDENCE_DIR`; new endpoint after `add_evidence`)
- Test: `tests/test_evidence_file.py` (add fixture + upload tests)

- [ ] **Step 1: Add the DB fixture + failing upload tests to `tests/test_evidence_file.py`**

Append:

```python
from app.core.database import AsyncSessionLocal
from app.models.governance import (
    Framework, Requirement, Assessment, RequirementAssessment, Evidence,
)


@pytest_asyncio.fixture
async def req_assessment():
    """Seed Framework -> Requirement -> Assessment -> RequirementAssessment; yield ids.

    Unique URNs per run so the shared (non-transactional) test DB won't trip
    unique constraints from prior runs.
    """
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as s:
        fw = Framework(urn=f"urn:test:fw:{tag}", name=f"FW {tag}")
        s.add(fw); await s.commit(); await s.refresh(fw)

        req = Requirement(framework_id=fw.id, urn=f"urn:test:req:{tag}",
                          ref_id="A.1", name="Req A.1")
        s.add(req); await s.commit(); await s.refresh(req)

        asmt = Assessment(name=f"Assessment {tag}", framework_id=fw.id)
        s.add(asmt); await s.commit(); await s.refresh(asmt)

        ra = RequirementAssessment(assessment_id=asmt.id, requirement_id=req.id)
        s.add(ra); await s.commit(); await s.refresh(ra)

        ids = {"ra_id": ra.id, "fw_id": fw.id, "req_id": req.id, "asmt_id": asmt.id}
        yield ids

        # Cleanup (children first). Evidence rows cascade on RA delete, but
        # delete explicitly so file rows from tests are gone too.
        await s.execute(Evidence.__table__.delete().where(
            Evidence.requirement_assessment_id == ra.id))
        await s.execute(RequirementAssessment.__table__.delete().where(
            RequirementAssessment.id == ra.id))
        await s.execute(Assessment.__table__.delete().where(Assessment.id == asmt.id))
        await s.execute(Requirement.__table__.delete().where(Requirement.id == req.id))
        await s.execute(Framework.__table__.delete().where(Framework.id == fw.id))
        await s.commit()


@pytest.mark.asyncio
async def test_upload_creates_file_and_row(req_assessment, monkeypatch, tmp_path):
    from app.routers import governance as gov
    monkeypatch.setattr(gov, "EVIDENCE_DIR", str(tmp_path))

    async with AsyncSessionLocal() as db:
        ev = await gov.add_evidence_file(
            ra_id=req_assessment["ra_id"],
            file=_upload(GOOD_PDF, "proof.pdf", "application/pdf"),
            name="My proof",
            description="a pdf",
            db=db,
            current_user=SimpleNamespace(user_id=1),
        )

    assert ev.kind == "file"
    assert ev.mime_type == "application/pdf"
    assert ev.size_bytes == len(GOOD_PDF)
    assert ev.name == "My proof"
    assert "/" not in ev.file_path and "\\" not in ev.file_path
    assert os.path.isfile(os.path.join(str(tmp_path), ev.file_path))


@pytest.mark.asyncio
async def test_upload_rejects_bad_magic(req_assessment, monkeypatch, tmp_path):
    from fastapi import HTTPException
    from app.routers import governance as gov
    monkeypatch.setattr(gov, "EVIDENCE_DIR", str(tmp_path))

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await gov.add_evidence_file(
                ra_id=req_assessment["ra_id"],
                file=_upload(b"not-a-png-xxxx", "x.png", "image/png"),
                name="bad", description=None, db=db,
                current_user=SimpleNamespace(user_id=1),
            )
    assert ei.value.status_code == 400
    assert not list(tmp_path.iterdir())  # nothing written


@pytest.mark.asyncio
async def test_upload_404_when_ra_missing(monkeypatch, tmp_path):
    from fastapi import HTTPException
    from app.routers import governance as gov
    monkeypatch.setattr(gov, "EVIDENCE_DIR", str(tmp_path))

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as ei:
            await gov.add_evidence_file(
                ra_id=999_999_999,
                file=_upload(GOOD_PDF, "p.pdf", "application/pdf"),
                name="x", description=None, db=db,
                current_user=SimpleNamespace(user_id=1),
            )
    assert ei.value.status_code == 404
```

- [ ] **Step 2: Run — expect FAIL**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -k upload -v`
Expected: FAIL with `AttributeError: module 'app.routers.governance' has no attribute 'add_evidence_file'` (and `EVIDENCE_DIR`).

- [ ] **Step 3: Add imports + `EVIDENCE_DIR` + endpoint to `app/routers/governance.py`**

Update the FastAPI import line at the top:

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
```

Add near the other top-level imports:

```python
import os
import uuid as _uuid
from app.core.uploads import validate_and_read_upload
```

Add a module-level constant after the imports (near the top, before the router endpoints):

```python
EVIDENCE_DIR = os.environ.get("CYBERGUARD_EVIDENCE_DIR", "/data/evidence")
```

Add this endpoint directly **after** the existing `add_evidence` function (the JSON url/text one):

```python
@router.post(
    "/governance/req-assessments/{ra_id}/evidence/file",
    response_model=EvidenceRead, status_code=201,
)
async def add_evidence_file(
    ra_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Upload a file as evidence for a requirement assessment (kind='file')."""
    ra = await db.get(RequirementAssessment, ra_id)
    if not ra:
        raise HTTPException(404, "Requirement assessment not found")

    content, mime = await validate_and_read_upload(file)

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    fname = _uuid.uuid4().hex
    with open(os.path.join(EVIDENCE_DIR, fname), "wb") as fh:
        fh.write(content)

    ev = Evidence(
        requirement_assessment_id=ra_id,
        name=name,
        description=description,
        kind="file",
        file_path=fname,
        mime_type=mime,
        size_bytes=len(content),
        uploaded_by_user_id=current_user.user_id,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return EvidenceRead.model_validate(ev)
```

(`AuthenticatedUser`, `RequirementAssessment`, `Evidence`, `EvidenceRead`, `Permission`, `require_permission`, `get_db` are already imported/used by the existing evidence endpoints — verify by reading the import block.)

- [ ] **Step 4: Run — expect PASS**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -k upload -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/governance.py tests/test_evidence_file.py
git commit -m "feat(governance): add multipart evidence file upload endpoint"
```

---

## Task 3: Download endpoint `GET /governance/evidence/{ev_id}/download`

**Files:**
- Modify: `app/routers/governance.py` (new endpoint after `add_evidence_file`)
- Test: `tests/test_evidence_file.py`

- [ ] **Step 1: Add failing download tests**

Append to `tests/test_evidence_file.py`:

```python
@pytest.mark.asyncio
async def test_download_returns_stored_bytes(req_assessment, monkeypatch, tmp_path):
    from app.routers import governance as gov
    monkeypatch.setattr(gov, "EVIDENCE_DIR", str(tmp_path))

    async with AsyncSessionLocal() as db:
        ev = await gov.add_evidence_file(
            ra_id=req_assessment["ra_id"],
            file=_upload(GOOD_PDF, "proof.pdf", "application/pdf"),
            name="proof.pdf", description=None, db=db,
            current_user=SimpleNamespace(user_id=1),
        )
        resp = await gov.download_evidence(
            ev_id=ev.id, db=db, _=SimpleNamespace(user_id=1))

    assert resp.media_type == "application/pdf"
    assert resp.filename == "proof.pdf"
    with open(resp.path, "rb") as fh:
        assert fh.read() == GOOD_PDF


@pytest.mark.asyncio
async def test_download_404_for_non_file_evidence(req_assessment, monkeypatch, tmp_path):
    from fastapi import HTTPException
    from app.routers import governance as gov
    monkeypatch.setattr(gov, "EVIDENCE_DIR", str(tmp_path))

    # Seed a text evidence directly.
    async with AsyncSessionLocal() as db:
        ev = Evidence(requirement_assessment_id=req_assessment["ra_id"],
                      name="note", kind="text", body="hi")
        db.add(ev); await db.commit(); await db.refresh(ev)
        with pytest.raises(HTTPException) as ei:
            await gov.download_evidence(ev_id=ev.id, db=db, _=SimpleNamespace(user_id=1))
    assert ei.value.status_code == 404
```

- [ ] **Step 2: Run — expect FAIL**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -k download -v`
Expected: FAIL — `module 'app.routers.governance' has no attribute 'download_evidence'`.

- [ ] **Step 3: Add the download endpoint**

In `app/routers/governance.py`, directly after `add_evidence_file`:

```python
@router.get("/governance/evidence/{ev_id}/download")
async def download_evidence(
    ev_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    """Download a file-kind evidence's stored content (authenticated)."""
    ev = await db.get(Evidence, ev_id)
    if not ev or ev.kind != "file" or not ev.file_path:
        raise HTTPException(404, "File evidence not found")

    base = os.path.abspath(EVIDENCE_DIR)
    full = os.path.abspath(os.path.join(base, ev.file_path))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        raise HTTPException(404, "Stored file not found")

    return FileResponse(
        full,
        media_type=ev.mime_type or "application/octet-stream",
        filename=ev.name,
    )
```

- [ ] **Step 4: Run — expect PASS**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -k download -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/routers/governance.py tests/test_evidence_file.py
git commit -m "feat(governance): add authenticated evidence file download endpoint"
```

---

## Task 4: Delete removes the stored file

**Files:**
- Modify: `app/routers/governance.py` (`delete_evidence`)
- Test: `tests/test_evidence_file.py`

- [ ] **Step 1: Add failing delete test**

Append to `tests/test_evidence_file.py`:

```python
@pytest.mark.asyncio
async def test_delete_file_evidence_removes_disk_file(req_assessment, monkeypatch, tmp_path):
    from app.routers import governance as gov
    monkeypatch.setattr(gov, "EVIDENCE_DIR", str(tmp_path))

    async with AsyncSessionLocal() as db:
        ev = await gov.add_evidence_file(
            ra_id=req_assessment["ra_id"],
            file=_upload(GOOD_PDF, "proof.pdf", "application/pdf"),
            name="proof.pdf", description=None, db=db,
            current_user=SimpleNamespace(user_id=1),
        )
        disk = os.path.join(str(tmp_path), ev.file_path)
        assert os.path.isfile(disk)
        ev_id = ev.id

        await gov.delete_evidence(ev_id=ev_id, db=db, _=SimpleNamespace(user_id=1))

        assert not os.path.exists(disk)            # file gone
        assert await db.get(Evidence, ev_id) is None  # row gone
```

(Confirm the existing `delete_evidence` signature's authenticated-user parameter name. If it is `_`, the call above is correct; if it is named differently, pass it by that keyword.)

- [ ] **Step 2: Run — expect FAIL**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -k delete_file -v`
Expected: FAIL — the disk file still exists (`assert not os.path.exists(disk)`).

- [ ] **Step 3: Add file cleanup to `delete_evidence`**

In `app/routers/governance.py`, in `delete_evidence`, after the `ev` 404 check and **before** `await db.delete(ev)`, insert:

```python
    if ev.kind == "file" and ev.file_path:
        base = os.path.abspath(EVIDENCE_DIR)
        full = os.path.abspath(os.path.join(base, ev.file_path))
        if full.startswith(base + os.sep):
            try:
                os.remove(full)
            except FileNotFoundError:
                pass
```

- [ ] **Step 4: Run — expect PASS, then the whole file**

Run: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest tests/test_evidence_file.py -v`
Expected: all evidence-file tests pass (validator 4 + upload 3 + download 2 + delete 1 = 10).

- [ ] **Step 5: Commit**

```bash
git add app/routers/governance.py tests/test_evidence_file.py
git commit -m "feat(governance): delete_evidence removes the stored file for kind=file"
```

---

## Task 5: Docker Compose volume for evidence storage

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Mount a named volume on the `api` service**

In `docker-compose.yml`, the `api` service currently has:

```yaml
    volumes:
      - ./app:/app/app
```

Change it to:

```yaml
    volumes:
      - ./app:/app/app
      - evidence_data:/data/evidence
```

- [ ] **Step 2: Declare the named volume**

The top-level `volumes:` section currently reads:

```yaml
volumes:
  postgres_data:
  redis_data:
  celerybeat_data:
```

Change it to:

```yaml
volumes:
  postgres_data:
  redis_data:
  celerybeat_data:
  evidence_data:
```

(`EVIDENCE_DIR` defaults to `/data/evidence`, which matches the mount — no extra env var needed.)

- [ ] **Step 3: Validate compose config**

Run: `docker compose config >/dev/null && echo "compose ok"`
Expected: `compose ok` (no YAML/schema error).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): add evidence_data volume for governance evidence files"
```

---

## Task 6: Frontend API client — `uploadEvidenceFile` + `downloadEvidence`

**Files:**
- Modify: `webui/src/api/client.ts`

- [ ] **Step 1: Add the two methods**

In `webui/src/api/client.ts`, directly after the existing `deleteEvidence` method, add:

```typescript
  uploadEvidenceFile: async (raId: number, file: File, name: string, description?: string) => {
    const token = localStorage.getItem('token')
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    if (description) fd.append('description', description)
    const res = await fetch(`${BASE}/governance/req-assessments/${raId}/evidence/file`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) }, // no Content-Type: browser sets multipart boundary
      body: fd,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  downloadEvidence: async (id: number, filename: string) => {
    const token = localStorage.getItem('token')
    const res = await fetch(`${BASE}/governance/evidence/${id}/download`, {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    if (!res.ok) throw new Error(await res.text())
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
```

- [ ] **Step 2: Type-check**

Run: `cd webui && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add webui/src/api/client.ts
git commit -m "feat(webui): add uploadEvidenceFile + downloadEvidence API client methods"
```

---

## Task 7: Frontend Governance form — file kind + download button

**Files:**
- Modify: `webui/src/pages/Governance.tsx`

- [ ] **Step 1: Widen the `Evidence` interface**

In `webui/src/pages/Governance.tsx`, change the `Evidence` interface to add the file fields:

```tsx
interface Evidence {
  id: number
  name: string
  description: string | null
  kind: 'file' | 'url' | 'text'
  url: string | null
  body: string | null
  file_path: string | null
  mime_type: string | null
  size_bytes: number | null
  uploaded_at: string
}
```

- [ ] **Step 2: Widen the add-form state**

Change the `newEvidence` state initializer (currently `useState({ name: '', body: '', kind: 'text' as 'text' | 'url', url: '' })`) to include `file` and allow `'file'`:

```tsx
  const [newEvidence, setNewEvidence] = useState<{
    name: string; body: string; kind: 'text' | 'url' | 'file'; url: string; file: File | null
  }>({ name: '', body: '', kind: 'text', url: '', file: null })
```

Find the two reset calls `setNewEvidence({ name: '', body: '', kind: 'text', url: '' })` (in `addEvidence` success and elsewhere) and update each to include `file: null`:

```tsx
      setNewEvidence({ name: '', body: '', kind: 'text', url: '', file: null })
```

- [ ] **Step 3: Add the FILE option + file input to the form**

In the `addingEv` form block, change the kind `<select>` onChange cast and add the option:

```tsx
                <select value={newEvidence.kind}
                  onChange={e => setNewEvidence(s => ({ ...s, kind: e.target.value as 'text' | 'url' | 'file' }))}
                  style={inputStyle()}>
                  <option value="text">TEXT</option>
                  <option value="url">URL</option>
                  <option value="file">FILE</option>
                </select>
```

Replace the `newEvidence.kind === 'text' ? (...) : (...)` ternary that renders the body/url inputs with a three-way render that also handles file:

```tsx
                {newEvidence.kind === 'text' && (
                  <textarea value={newEvidence.body} onChange={e => setNewEvidence(s => ({ ...s, body: e.target.value }))}
                    rows={4} placeholder="Paste log excerpt, policy text, etc." style={textareaStyle()} />
                )}
                {newEvidence.kind === 'url' && (
                  <input value={newEvidence.url} onChange={e => setNewEvidence(s => ({ ...s, url: e.target.value }))}
                    placeholder="https://..." style={inputStyle()} />
                )}
                {newEvidence.kind === 'file' && (
                  <input type="file"
                    onChange={e => setNewEvidence(s => ({ ...s, file: e.target.files?.[0] ?? null }))}
                    style={inputStyle()} />
                )}
```

- [ ] **Step 4: Branch `addEvidence` for the file kind**

Replace the body of `addEvidence` with a version that handles all three kinds (this preserves the existing url/text JSON path and adds the multipart path):

```tsx
  const addEvidence = async () => {
    if (!newEvidence.name.trim()) { alert('Name is required'); return }
    if (newEvidence.kind === 'text' && !newEvidence.body.trim()) { alert('Body is required for text evidence'); return }
    if (newEvidence.kind === 'url' && !newEvidence.url.trim()) { alert('URL is required'); return }
    if (newEvidence.kind === 'file' && !newEvidence.file) { alert('Choose a file'); return }
    setSavingEv(true)
    try {
      let ev: Evidence
      if (newEvidence.kind === 'file') {
        ev = await api.uploadEvidenceFile(ra.id, newEvidence.file!, newEvidence.name.trim()) as Evidence
      } else {
        ev = await api.addEvidence(ra.id, {
          name: newEvidence.name.trim(),
          kind: newEvidence.kind,
          body: newEvidence.kind === 'text' ? newEvidence.body : undefined,
          url: newEvidence.kind === 'url' ? newEvidence.url : undefined,
        }) as Evidence
      }
      onUpdate({ evidences: [ev, ...ra.evidences] })
      setNewEvidence({ name: '', body: '', kind: 'text', url: '', file: null })
      setAddingEv(false)
    } catch (e: any) { alert(e.message) }
    finally { setSavingEv(false) }
  }
```

- [ ] **Step 5: Add a download button + size to the evidence row**

In the `ra.evidences.map(ev => ...)` row, inside the `<div style={{ flex: 1, minWidth: 0 }}>` (after the existing url/text conditionals), add a file branch:

```tsx
                      {ev.kind === 'file' && (
                        <button onClick={() => api.downloadEvidence(ev.id, ev.name)}
                          style={{ color: 'var(--accent)', background: 'none', border: 'none',
                            padding: 0, cursor: 'pointer', textAlign: 'left' }}>
                          ⬇ {ev.name}{ev.size_bytes != null ? ` (${Math.ceil(ev.size_bytes / 1024)} KB)` : ''}
                        </button>
                      )}
```

- [ ] **Step 6: Type-check and build**

Run: `cd webui && npm run build`
Expected: 0 TypeScript errors. (Pre-existing CSS `@import` ordering warning and the chunk-size warning are unrelated.)

- [ ] **Step 7: Manual smoke (optional but recommended)**

Bring the stack up (`docker compose up -d`), open Governance → an assessment → a requirement row → EVIDENCE → ADD → kind FILE, choose a small PDF, ADD. Confirm it appears with a download link; click it and confirm the file downloads; delete it and confirm it disappears.

- [ ] **Step 8: Commit**

```bash
git add webui/src/pages/Governance.tsx
git commit -m "feat(webui): governance evidence file upload + download in the UI"
```

---

## Final verification

- [ ] Whole backend suite with postgres up:

```bash
docker compose up -d postgres
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard" .venv/bin/python -m pytest -q
```

Expected: previously-green tests + the 10 new evidence-file tests pass; only the 3 known environmental `TestMasterAgentStateMachine` redis failures remain.

- [ ] Frontend builds clean: `cd webui && npm run build` → 0 errors.

- [ ] Update `docs/superpowers/plans/project_status.md`: remove "Governance evidence 文件上传" from "Not yet implemented" and add a line under "Recently completed" describing the new upload/download endpoints, the `evidence_data` volume, and the Governance UI file kind.

- [ ] Use `superpowers:finishing-a-development-branch` to decide merge/PR.
```
