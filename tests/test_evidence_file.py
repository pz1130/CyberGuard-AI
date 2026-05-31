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


@pytest.mark.asyncio
async def test_validate_rejects_short_magic_mismatch():
    """A file shorter than 8 bytes but >= the signature length must still be
    magic-checked (regression guard for the len(expected) guard)."""
    from fastapi import HTTPException
    from app.core.uploads import validate_and_read_upload
    # 4 bytes, declared pdf, but not "%PDF".
    with pytest.raises(HTTPException) as ei:
        await validate_and_read_upload(_upload(b"xxxx", "a.pdf", "application/pdf"))
    assert ei.value.status_code == 400


from app.core.database import AsyncSessionLocal
from app.models.governance import (
    Framework, Requirement, ComplianceAssessment, RequirementAssessment, Evidence,
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

        asmt = ComplianceAssessment(name=f"Assessment {tag}", framework_id=fw.id)
        s.add(asmt); await s.commit(); await s.refresh(asmt)

        ra = RequirementAssessment(assessment_id=asmt.id, requirement_id=req.id)
        s.add(ra); await s.commit(); await s.refresh(ra)

        ids = {"ra_id": ra.id, "fw_id": fw.id, "req_id": req.id, "asmt_id": asmt.id}
        yield ids

        # Cleanup (children first; respect RESTRICT FKs).
        await s.execute(Evidence.__table__.delete().where(
            Evidence.requirement_assessment_id == ra.id))
        await s.execute(RequirementAssessment.__table__.delete().where(
            RequirementAssessment.id == ra.id))
        await s.execute(ComplianceAssessment.__table__.delete().where(
            ComplianceAssessment.id == asmt.id))
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
