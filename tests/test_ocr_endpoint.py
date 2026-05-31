import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_upload_scanned_enabled_returns_202(monkeypatch):
    from app.routers import knowledge as kn
    from app.services.ocr_service import ScannedPdfError, OcrSettings

    monkeypatch.setattr(kn, "extract_text", lambda *a, **k: (_ for _ in ()).throw(ScannedPdfError("scan")))
    monkeypatch.setattr(kn, "load_ocr_config",
                        AsyncMock(return_value=OcrSettings(True, "tesseract", "eng", 30, None, None)))
    fake_doc = SimpleNamespace(id=7)
    fake_svc = SimpleNamespace(
        create_pending_document=AsyncMock(return_value=fake_doc),
        ingest_document=AsyncMock())
    monkeypatch.setattr(kn, "get_knowledge_service", lambda: fake_svc)

    class _F:
        filename = "scan.pdf"; content_type = "application/pdf"
        async def read(self): return b"%PDF scan"

    with patch("app.workers.tasks.ocr_ingest_task.delay") as mock_delay:
        resp = await kn.upload_document(kb_id=1, file=_F(), provider_id=None,
                                        db=AsyncMock(), _=None)
    import json
    body = json.loads(bytes(resp.body).decode())
    assert resp.status_code == 202
    assert body["status"] == "processing"
    assert body["document_id"] == 7
    mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_upload_scanned_disabled_returns_400(monkeypatch):
    from app.routers import knowledge as kn
    from app.services.ocr_service import ScannedPdfError, OcrSettings
    from fastapi import HTTPException

    monkeypatch.setattr(kn, "extract_text", lambda *a, **k: (_ for _ in ()).throw(ScannedPdfError("scan")))
    monkeypatch.setattr(kn, "load_ocr_config",
                        AsyncMock(return_value=OcrSettings(False, "tesseract", "eng", 30, None, None)))

    class _F:
        filename = "scan.pdf"; content_type = "application/pdf"
        async def read(self): return b"%PDF scan"

    with pytest.raises(HTTPException) as ei:
        await kn.upload_document(kb_id=1, file=_F(), provider_id=None, db=AsyncMock(), _=None)
    assert ei.value.status_code == 400


def test_document_response_includes_status():
    from types import SimpleNamespace
    from datetime import datetime
    from app.schemas.knowledge import DocumentResponse
    obj = SimpleNamespace(
        id=1, kb_id=2, filename="s.pdf", content_chunks_json=None,
        file_hash="x", file_size=3, mime_type="application/pdf",
        metadata_json={}, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        status="processing", status_detail=None)
    dumped = DocumentResponse.model_validate(obj).model_dump()
    assert dumped["status"] == "processing"
    assert "status_detail" in dumped
