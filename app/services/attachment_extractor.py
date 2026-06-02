"""Extract plain text from chat attachments for injection into the agent prompt.

Reuses knowledge_service.extract_text (pypdf / docx / utf-8) and ocr_service
(scanned-PDF + image OCR). Every branch degrades to a marker string on failure
so one bad attachment never aborts an agent run. See
docs/superpowers/specs/2026-06-02-chat-attachment-extraction-design.md
"""
from __future__ import annotations

import base64
import logging

from app.services.knowledge_service import extract_text
from app.services.ocr_service import OcrSettings, ScannedPdfError, ocr_image, ocr_pdf

logger = logging.getLogger(__name__)

_TEXT_TYPES = {"text/plain", "text/markdown", "text/csv"}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

_OCR_DISABLED_MARKER = "(OCR 未启用，无法提取图片/扫描件内容)"


async def extract_attachment_text(
    raw: bytes,
    content_type: str,
    filename: str,
    cfg: OcrSettings,
) -> str:
    """Return extracted text for one attachment, or a short marker on failure."""
    ct = (content_type or "").lower()
    try:
        if ct in _TEXT_TYPES:
            return raw.decode("utf-8", errors="replace")

        if ct == "application/pdf":
            try:
                return extract_text(raw, ct, filename)
            except ScannedPdfError:  # raised by extract_text when a PDF has no text layer
                if not cfg.enabled:
                    return _OCR_DISABLED_MARKER
                return await ocr_pdf(raw, cfg)

        if ct in _IMAGE_TYPES:
            if not cfg.enabled:
                return _OCR_DISABLED_MARKER
            return await ocr_image(raw, cfg)

        # Unreachable: upload validation restricts to the types above.
        return ""
    except Exception as e:  # noqa: BLE001 - extraction must not crash the run
        logger.warning("attachment extraction failed for %r (%s): %s",
                       filename, content_type, e)
        return f"(提取失败: {e})"


def cap_text(text: str, limit: int) -> str:
    """Return text unchanged if within limit, else truncate + append a marker."""
    if len(text) <= limit:
        return text
    dropped = len(text) - limit
    return f"{text[:limit]}\n...[truncated {dropped} chars]"


async def build_attachment_section(
    attachments: list[dict],
    cfg: OcrSettings,
    *,
    per_cap: int,
    total_cap: int,
) -> str:
    """Decode + extract + cap + format a list of attachment dicts.

    Each dict has keys: filename, content_type, data (base64 str). Returns the
    full block to append to user_input (with the '--- 附件信息 ---' header), or
    '' when there are no attachments.
    """
    if not attachments:
        return ""

    lines: list[str] = []
    for att in attachments:
        filename = att.get("filename") or "attachment"
        content_type = att.get("content_type") or ""
        try:
            raw = base64.b64decode(att.get("data", ""), validate=True)
            text = await extract_attachment_text(raw, content_type, filename, cfg)
        except Exception as e:  # noqa: BLE001 - bad payload must not crash the run
            logger.warning("attachment decode failed for %r: %s", filename, e)
            text = f"(提取失败: {e})"
        capped = cap_text(text, per_cap)
        lines.append(f"[附件: {filename}] (type: {content_type})\n{capped}")

    body = cap_text("\n\n".join(lines), total_cap)
    return f"\n\n--- 附件信息 ---\n{body}"
