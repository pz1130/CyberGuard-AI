# Chat Attachment Extraction — Design

**Issue:** [#13](https://github.com/pz1130/CyberGuard-AI/issues/13) — Chat attachments: handle binary/image/PDF (not just truncated UTF-8 text)
**Date:** 2026-06-02
**Status:** Approved (brainstorming)

## Problem

Chat attachments are accepted, validated, base64-encoded, stored on the
`AgentExecution`, and dispatched to the Celery worker. But the worker
(`app/workers/tasks.py`) only makes them "meaningful" by base64-decoding each
payload as **UTF-8 and truncating to 1000 chars**. Consequently:

- **Binary / image / PDF attachments decode to replacement-character garbage**
  and add no useful signal to the agent.
- There is **no vision or OCR routing** in the chat path. OCR exists, but only
  for the knowledge/evidence ingestion flow — not chat uploads.
- Real text content is silently cut at 1000 chars (a multi-page PDF becomes a
  paragraph).

Upload validation (`app/core/uploads.py`) already restricts attachments to:
`image/png`, `image/jpeg`, `image/gif`, `image/webp`, `application/pdf`,
`text/plain`, `text/markdown`, `text/csv` (≤10 MB each, ≤10 files).

## Approach

**Extract-to-text, reusing existing toolkits** (chosen over true multimodal
passthrough). The chat LLM path (`llm_router`) is text-only and has no
multimodal support; adding it would touch the provider abstraction and only
work on vision-capable providers. Instead we convert every attachment to text
before injecting it into `user_input`, reusing:

- `knowledge_service.extract_text(raw, mime, filename)` — pypdf (PDF), python-docx,
  utf-8 decode. Raises `ScannedPdfError` when a PDF has no extractable text.
- `ocr_service` — scanned-PDF and image OCR via Tesseract **or** a vision model,
  driven by the stored OCR config.

Images still "use vision" via `ocr_service`'s vision OCR engine — but only to
produce text, with no `llm_router` changes.

## Components

### 1. `app/services/attachment_extractor.py` (new)

One focused, independently testable unit:

```python
async def extract_attachment_text(
    raw: bytes,
    content_type: str,
    filename: str,
    cfg: OcrSettings,
) -> str:
    ...
```

Routing (every branch wrapped so failure returns a marker string, never raises):

| Content type | Path |
|---|---|
| `text/plain`, `text/markdown`, `text/csv` | utf-8 decode (`errors="replace"`) |
| `application/pdf` | `extract_text()` (pypdf); on `ScannedPdfError` → `ocr_service.ocr_pdf(raw, cfg)` |
| `image/png`, `image/jpeg`, `image/gif`, `image/webp` | `ocr_service.ocr_image(raw, cfg)` |
| anything else | `""` (unreachable — upload validation restricts types) |

On any extraction error the function returns a short marker, e.g.
`"(提取失败: <reason>)"`, so the caller can attribute it to the file.

**OCR-disabled case:** when `cfg.enabled` is `False`, the image and scanned-PDF
branches skip OCR and return the marker `"(OCR 未启用，无法提取图片/扫描件内容)"`.
Text files and text-layer PDFs are unaffected (they don't need OCR).

### 2. `app/services/ocr_service.py` (addition)

New public wrapper mirroring `ocr_pdf`, so the extractor never touches internals:

```python
async def ocr_image(raw: bytes, cfg: OcrSettings) -> str:
    """OCR a single image (Tesseract or vision, per cfg.engine)."""
```

Engine selection matches `ocr_pdf`: `cfg.engine == "vision" and
cfg.vision_provider_id` → `_ocr_vision([raw], ...)`, else
`_ocr_tesseract([raw], ...)`. Unlike `ocr_pdf`, the image bytes are passed
**directly** as the single-element list — no rasterization step (the payload is
already an image; PIL/Tesseract and the vision data-URL both accept
png/jpeg/gif/webp).

### 3. Worker integration — `app/workers/tasks.py`

Replace the current base64→utf-8 injection block. Because OCR is async, the
attachment processing moves **inside** the existing event loop (the `_run`
coroutine that already runs via `run_until_complete`), rather than the current
synchronous pre-step.

Per request:
1. `cfg = await load_ocr_config()` once.
2. For each attachment: base64-decode `data` → bytes; `text =
   await extract_attachment_text(raw, content_type, filename, cfg)`; apply the
   per-attachment cap; format as `"[附件: <filename>] (type: <content_type>)\n<text>"`.
3. Enforce the total cap across all attachments.
4. Append the joined block to `user_input` under a `--- 附件信息 ---` header
   (unchanged framing).

### 4. Configuration — `app/config.py`

Two new settings (replace the hard-coded 1000):

- `ATTACHMENT_MAX_CHARS: int = 8000` — per-attachment cap.
- `ATTACHMENT_TOTAL_MAX_CHARS: int = 24000` — cap across all attachments in one request.

When extracted text exceeds a cap, the kept portion is followed by
`"\n...[truncated <N> chars]"`.

## Error handling

- **Per-attachment failure** (parse error, OCR engine missing, no vision provider
  configured) → inject `"[附件: <filename>] (提取失败: <reason>)"` and continue.
  One bad file never aborts the agent run.
- **Scanned PDF** → detected via `ScannedPdfError` from `extract_text`, then OCR
  fallback. If OCR is also unavailable, falls through to the failure marker.

## Testing (TDD)

Unit — `tests/test_attachment_extractor.py`:
- text/plain, text/markdown, text/csv → decoded text.
- text PDF → `extract_text` result (pypdf mocked).
- scanned PDF → `ScannedPdfError` triggers `ocr_pdf` fallback (both mocked).
- image/* → `ocr_image` result (mocked).
- OCR disabled (`cfg.enabled == False`) → image / scanned-PDF return the
  "OCR 未启用" marker; text files unaffected.
- extraction failure → marker string, no raise.
- capping: per-attachment and total truncation markers (pure-function level).

Integration — worker test (in existing worker test module or new):
- `attachments` kwarg produces an augmented `user_input` containing the
  extracted text and `--- 附件信息 ---` header (extractor mocked).

## Out of scope (YAGNI)

- Multimodal LLM passthrough (native image input to a vision model in chat).
- LLM summarization of over-cap documents.
- New file types beyond the currently-allowed set.
- Persisting extracted text back to the DB / attachment records.
