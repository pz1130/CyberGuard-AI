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
