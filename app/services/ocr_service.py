"""OCR for scanned PDFs: detection, rasterization, Tesseract / vision engines."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from dataclasses import dataclass
from typing import List, Optional

import fitz  # PyMuPDF
import pytesseract

from app.core.database import AsyncSessionLocal
from app.services.llm_router import get_llm_router

logger = logging.getLogger(__name__)


class ScannedPdfError(ValueError):
    """Raised when a PDF has no extractable text layer (likely scanned)."""


@dataclass
class OcrSettings:
    enabled: bool
    engine: str            # "tesseract" | "vision"
    languages: str         # e.g. "chi_sim+eng"
    max_pages: int
    vision_provider_id: Optional[int]
    vision_model: Optional[str]


def pdf_is_scanned(raw: bytes) -> bool:
    """True when no page yields non-empty text via the PDF text layer."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        for page in reader.pages:
            try:
                if (page.extract_text() or "").strip():
                    return False
            except Exception:
                continue
        return True
    except Exception as e:
        logger.warning("[pdf_is_scanned] read failed, treating as scanned: %s", e)
        return True


def rasterize_pdf(raw: bytes, max_pages: int) -> List[bytes]:
    """Render up to max_pages to PNG bytes (150 DPI)."""
    images: List[bytes] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=150)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


async def ocr_pdf(raw: bytes, cfg: OcrSettings) -> str:
    """Rasterize then OCR each page; join page texts with blank lines."""
    images = rasterize_pdf(raw, cfg.max_pages)
    if not images:
        return ""
    if cfg.engine == "vision" and cfg.vision_provider_id:
        return await _ocr_vision(images, cfg.vision_provider_id, cfg.vision_model)
    return await _ocr_tesseract(images, cfg.languages)


async def ocr_image(raw: bytes, cfg: OcrSettings) -> str:
    """OCR a single image (Tesseract or vision, per cfg.engine).

    Unlike ocr_pdf there is no rasterization step — the payload is already an
    image, so it is passed through as a single-element list. PIL/Tesseract and
    the vision data-URL both accept png/jpeg/gif/webp.
    """
    if cfg.engine == "vision" and cfg.vision_provider_id:
        return await _ocr_vision([raw], cfg.vision_provider_id, cfg.vision_model)
    return await _ocr_tesseract([raw], cfg.languages)


async def _ocr_tesseract(images: List[bytes], languages: str) -> str:
    from PIL import Image

    def _run(img_bytes: bytes) -> str:
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img, lang=languages)

    pages = []
    for img_bytes in images:
        pages.append((await asyncio.to_thread(_run, img_bytes)).strip())
    return "\n\n".join(p for p in pages if p)


async def _ocr_vision(images: List[bytes], provider_id: int, model: Optional[str]) -> str:
    router = get_llm_router()
    pages = []
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode()
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "请逐字转录这张图片中的所有文字，只输出文字本身，不要解释。"},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }]
        text = await router.chat(messages=messages, provider_id=provider_id, model=model)
        pages.append((text if isinstance(text, str) else getattr(text, "content", "") or "").strip())
    return "\n\n".join(p for p in pages if p)


def settings_from_row(row) -> OcrSettings:
    """Build OcrSettings from an OcrConfig row, or defaults when row is None."""
    if row is None:
        return OcrSettings(enabled=True, engine="tesseract", languages="chi_sim+eng",
                           max_pages=30, vision_provider_id=None, vision_model=None)
    return OcrSettings(
        enabled=row.enabled, engine=row.engine, languages=row.languages,
        max_pages=row.max_pages, vision_provider_id=row.vision_provider_id,
        vision_model=row.vision_model,
    )


async def load_ocr_config() -> OcrSettings:
    """Return the single ocr_config row as OcrSettings, or defaults if none."""
    from sqlalchemy import select
    from app.models.ocr import OcrConfig

    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(OcrConfig))).scalar_one_or_none()
    return settings_from_row(row)
