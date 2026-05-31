import io
import pytest


def _one_page_text_pdf() -> bytes:
    """A 1-page PDF with a real text layer, built via fitz."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello text layer")
    out = doc.tobytes()
    doc.close()
    return out


def _one_page_blank_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page()  # blank, no text
    out = doc.tobytes()
    doc.close()
    return out


def test_pdf_is_scanned_false_for_text_pdf():
    from app.services.ocr_service import pdf_is_scanned
    assert pdf_is_scanned(_one_page_text_pdf()) is False


def test_pdf_is_scanned_true_for_blank_pdf():
    from app.services.ocr_service import pdf_is_scanned
    assert pdf_is_scanned(_one_page_blank_pdf()) is True


def test_rasterize_pdf_returns_png_bytes_per_page():
    from app.services.ocr_service import rasterize_pdf
    images = rasterize_pdf(_one_page_blank_pdf(), max_pages=30)
    assert len(images) == 1
    assert images[0][:8] == b"\x89PNG\r\n\x1a\n"


def test_rasterize_pdf_caps_at_max_pages():
    import fitz
    from app.services.ocr_service import rasterize_pdf
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    raw = doc.tobytes(); doc.close()
    assert len(rasterize_pdf(raw, max_pages=2)) == 2


@pytest.mark.asyncio
async def test_ocr_pdf_tesseract(monkeypatch):
    import app.services.ocr_service as ocr
    monkeypatch.setattr(ocr.pytesseract, "image_to_string", lambda img, lang=None: "PAGE TEXT")
    cfg = ocr.OcrSettings(enabled=True, engine="tesseract", languages="eng",
                          max_pages=30, vision_provider_id=None, vision_model=None)
    text = await ocr.ocr_pdf(_one_page_blank_pdf(), cfg)
    assert "PAGE TEXT" in text


@pytest.mark.asyncio
async def test_ocr_pdf_vision_calls_router(monkeypatch):
    import app.services.ocr_service as ocr
    from unittest.mock import AsyncMock
    fake_router = type("R", (), {"chat": AsyncMock(return_value="VISION TEXT")})()
    monkeypatch.setattr(ocr, "get_llm_router", lambda: fake_router)
    cfg = ocr.OcrSettings(enabled=True, engine="vision", languages="eng",
                          max_pages=30, vision_provider_id=1, vision_model="gpt-4o")
    text = await ocr.ocr_pdf(_one_page_blank_pdf(), cfg)
    assert "VISION TEXT" in text
    assert fake_router.chat.await_count == 1
