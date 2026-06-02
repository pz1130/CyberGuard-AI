import pytest

import app.services.attachment_extractor as ax
from app.services.ocr_service import OcrSettings, ScannedPdfError


def _cfg(enabled=True, engine="tesseract"):
    return OcrSettings(enabled=enabled, engine=engine, languages="eng",
                       max_pages=5, vision_provider_id=None, vision_model=None)


@pytest.mark.asyncio
async def test_text_plain_decoded():
    out = await ax.extract_attachment_text(b"hello world", "text/plain", "a.txt", _cfg())
    assert out == "hello world"


@pytest.mark.asyncio
async def test_text_markdown_decoded():
    out = await ax.extract_attachment_text(b"# Title", "text/markdown", "a.md", _cfg())
    assert out == "# Title"


@pytest.mark.asyncio
async def test_text_csv_decoded():
    out = await ax.extract_attachment_text(b"a,b\n1,2", "text/csv", "a.csv", _cfg())
    assert out == "a,b\n1,2"


@pytest.mark.asyncio
async def test_pdf_with_text_layer(monkeypatch):
    monkeypatch.setattr(ax, "extract_text", lambda raw, mime, fn: "PDF TEXT")
    out = await ax.extract_attachment_text(b"%PDF...", "application/pdf", "a.pdf", _cfg())
    assert out == "PDF TEXT"


@pytest.mark.asyncio
async def test_scanned_pdf_falls_back_to_ocr(monkeypatch):
    def raise_scanned(raw, mime, fn):
        raise ScannedPdfError("scanned")
    monkeypatch.setattr(ax, "extract_text", raise_scanned)

    async def fake_ocr_pdf(raw, cfg):
        return "OCR PDF"
    monkeypatch.setattr(ax, "ocr_pdf", fake_ocr_pdf)

    out = await ax.extract_attachment_text(b"%PDF...", "application/pdf", "a.pdf", _cfg())
    assert out == "OCR PDF"


@pytest.mark.asyncio
async def test_image_uses_ocr_image(monkeypatch):
    async def fake_ocr_image(raw, cfg):
        return "IMG OCR"
    monkeypatch.setattr(ax, "ocr_image", fake_ocr_image)

    out = await ax.extract_attachment_text(b"\x89PNG...", "image/png", "a.png", _cfg())
    assert out == "IMG OCR"


@pytest.mark.asyncio
async def test_image_with_ocr_disabled_returns_marker():
    out = await ax.extract_attachment_text(b"\x89PNG...", "image/png", "a.png",
                                           _cfg(enabled=False))
    assert "OCR 未启用" in out


@pytest.mark.asyncio
async def test_scanned_pdf_with_ocr_disabled_returns_marker(monkeypatch):
    def raise_scanned(raw, mime, fn):
        raise ScannedPdfError("scanned")
    monkeypatch.setattr(ax, "extract_text", raise_scanned)
    out = await ax.extract_attachment_text(b"%PDF...", "application/pdf", "a.pdf",
                                           _cfg(enabled=False))
    assert "OCR 未启用" in out


@pytest.mark.asyncio
async def test_extraction_failure_returns_marker(monkeypatch):
    def boom(raw, mime, fn):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(ax, "extract_text", boom)
    out = await ax.extract_attachment_text(b"%PDF...", "application/pdf", "a.pdf", _cfg())
    assert "提取失败" in out
    assert "kaboom" in out
