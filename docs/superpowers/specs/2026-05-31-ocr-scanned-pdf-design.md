---
name: ocr-scanned-pdf-design
description: Design for OCR of scanned/image-only PDFs in knowledge ingestion — pypdf text-layer fallback to OCR, Tesseract (default) or vision-LLM engine via a global setting, run asynchronously on Celery so the single-worker API is never blocked.
type: spec
date: 2026-05-31
status: approved
---

# OCR for Scanned PDFs — Design

## Goal

When a PDF uploaded to a knowledge base has no extractable text layer (a
scanned/image-only document), OCR it instead of failing. Support two engines —
local **Tesseract** (default, offline) and an optional **vision-LLM** mode —
selected by a global admin setting. Because OCR is slow and the API runs
single-worker, scanned-PDF ingestion runs **asynchronously on Celery**; normal
text PDFs keep their existing synchronous path unchanged.

## Decisions (locked during brainstorming)

- **Engines:** both. Tesseract is the default; vision-LLM is an admin-toggled
  high-accuracy mode. Per-KB / per-upload engine selection is out of scope
  (future increment).
- **Trigger:** fallback only, whole-document. OCR runs only when pypdf yields
  no text for the whole PDF. Per-page mixed handling and forced-OCR are out of
  scope.
- **Async:** scanned PDFs ingest via Celery; normal text PDFs stay in-request.
  Reason: the API is single-worker (see `multi-worker-blockers.md`); slow OCR in
  the request would freeze the whole API.
- **Engine switch location:** a single global `ocr_config` row (admin-only),
  mirroring the existing `SsoConfig` single-row pattern.

## Architecture / data flow

```
Upload PDF → POST /knowledge/bases/{kb_id}/documents (upload_document)
  1. extract_text(raw, ...)            # pypdf text layer — fast, synchronous
     ├─ text found  → ingest_document() synchronously → 201 {status: "ready"}   (unchanged path)
     └─ text empty  → raise ScannedPdfError   (new ValueError subclass)
  2. endpoint catches ScannedPdfError:
     ├─ OCR disabled → HTTP 400 ("扫描件 PDF 需启用 OCR")
     └─ OCR enabled  → create Document(status="processing")
                       → ocr_ingest_task.delay(doc_id, kb_id, base64(raw), ...)
                       → HTTP 202 {document_id, status: "processing"}
  3. Celery worker — ocr_ingest_task:
       rasterize (PyMuPDF) → engine (Tesseract | vision-LLM, per OcrConfig) → text
       → ingest_document(..., document_id=doc_id)   # chunk + embed into the existing row
       → Document.status = "ready"   (or "failed" + status_detail on error)
  4. Frontend document list polls status; refreshes when processing → ready/failed.
```

Passing the raw bytes to the worker as base64 reuses the established chat-
attachment pattern (`app/routers/chat.py` already base64-encodes uploads for the
worker). A file-size cap (≤20 MB) guards the broker.

## Data model (migration 016, head is currently 015)

**`documents` table — add two columns:**
- `status` `String(20)` not null, default `"ready"` — `ready` | `processing` | `failed`.
- `status_detail` `Text` nullable — failure reason for `failed`.

Existing rows and all text-path documents are `ready`. (The migration backfills
existing rows to `"ready"`.)

**New `ocr_config` table — single row, mirrors `SsoConfig`:**
- `id` PK
- `enabled` `Boolean` not null default `True`
- `engine` `String(20)` not null default `"tesseract"` — `tesseract` | `vision`
- `vision_provider_id` `Integer` FK `providers.id` nullable
- `vision_model` `String(255)` nullable
- `languages` `String(64)` not null default `"chi_sim+eng"`
- `max_pages` `Integer` not null default `30`
- `updated_at` `DateTime`

Read/write restricted to ADMIN.

## OCR service module — `app/services/ocr_service.py`

Single responsibility, independently testable.

```python
class ScannedPdfError(ValueError):
    """Raised when a PDF has no extractable text layer (likely scanned)."""

def pdf_is_scanned(raw: bytes) -> bool:
    """True when pypdf extracts no non-empty text across all pages."""

def rasterize_pdf(raw: bytes, max_pages: int) -> list[bytes]:
    """Render each page to a PNG (PyMuPDF / fitz). Caps at max_pages."""

async def ocr_pdf(raw: bytes, cfg) -> str:
    """Dispatch on cfg.engine; rasterize then OCR; join page texts with blank lines."""

async def _ocr_tesseract(images: list[bytes], languages: str) -> str:
    """pytesseract.image_to_string per page, wrapped in asyncio.to_thread."""

async def _ocr_vision(images: list[bytes], provider_id: int, model: str) -> str:
    """Per page: PNG → base64 → llm_router vision call ('transcribe this page,
    output only the text'). Falls back to Tesseract if no vision config, noting
    the fallback in the document's status_detail."""
```

- **Rasterization:** PyMuPDF (`fitz`) — pip-only, no poppler system dependency.
- **Tesseract:** `pytesseract.image_to_string(img, lang=languages)`, blocking,
  wrapped in `asyncio.to_thread`. Requires Docker system packages
  `tesseract-ocr` + `tesseract-ocr-chi-sim`.
- **Vision:** reuses the existing `llm_router`; one call per page.

### `extract_text()` change (`app/services/knowledge_service.py:58-59`)

Currently the empty-text branch raises
`ValueError("PDF contains no extractable text (likely scanned image).")`.
Change it to raise `ScannedPdfError(...)`. Because `ScannedPdfError` subclasses
`ValueError`, any existing caller that catches `ValueError` keeps its current
behavior; the upload endpoint gains a precise type to branch on. All other
`extract_text` logic (docx, txt, normal PDF) is unchanged.

## Celery task — `app/workers/tasks.py`

```python
@celery_app.task(bind=True, max_retries=1)
def ocr_ingest_task(self, document_id, kb_id, raw_b64, filename, mime_type):
    # run the async body via the file's existing run-async helper
    raw = base64.b64decode(raw_b64)
    try:
        cfg = await load_ocr_config()
        text = await ocr_pdf(raw, cfg)
        if not text.strip():
            raise ValueError("OCR 未识别出文字")
        await ingest_document(kb_id, content=text, filename=filename,
                              mime_type=mime_type, document_id=document_id)
        # set Document.status = "ready"
    except Exception as e:
        # set Document.status = "failed", status_detail = str(e)[:500]
```

`ingest_document` gains an optional `document_id` parameter: when provided, it
chunks + embeds into the **existing** (processing) Document row instead of
creating a new one. When omitted, behavior is unchanged (creates a new row).

## Endpoints

**`upload_document` (`app/routers/knowledge.py:129`) — add the scanned branch:**

```python
try:
    content = extract_text(raw, file.content_type, file.filename or "")
    doc = await service.ingest_document(kb_id, content, ...)   # 201 ready (unchanged)
except ScannedPdfError:
    cfg = await load_ocr_config()
    if not cfg.enabled:
        raise HTTPException(400, "扫描件 PDF 需启用 OCR（请在 OCR 设置中开启）")
    if len(raw) > MAX_OCR_BYTES:        # 20 MB
        raise HTTPException(413, "扫描件超出 OCR 大小上限")
    doc = await service.create_pending_document(kb_id, file.filename, file.content_type, raw)
    ocr_ingest_task.delay(doc.id, kb_id, base64.b64encode(raw).decode(), file.filename, file.content_type)
    return JSONResponse(status_code=202, content={"document_id": doc.id, "status": "processing"})
```

`create_pending_document` inserts a `Document(status="processing")` with
filename/mime/hash/size and no chunks yet.

**OCR settings (ADMIN):**
- `GET /ocr/config` → returns the row or defaults.
- `PUT /ocr/config` → upserts engine / enabled / vision_provider_id /
  vision_model / languages / max_pages.
- `load_ocr_config()` service returns the single row or an in-memory default
  (`enabled=True, engine="tesseract", languages="chi_sim+eng", max_pages=30`)
  when no row exists.

## Frontend (`webui/src/pages/Knowledge.tsx`)

- **Status badges** in the document list: `processing` (amber/spinner),
  `failed` (red; `status_detail` on hover), `ready` (green dot / none).
- **Polling:** while any document is `processing`, refresh the list every ~5 s;
  stop once all are `ready`/`failed`.
- **OCR settings panel** (admin-only, collapsible at top of Knowledge page):
  engine dropdown (Tesseract / Vision), enabled toggle, vision provider + model
  pickers (shown only when engine = Vision), languages, max_pages, save.
- **API client** (`webui/src/api/client.ts`): add `getOcrConfig` /
  `updateOcrConfig`. The upload flow surfaces the 202 as "扫描件，正在后台 OCR
  识别…" and shows the document as `processing`.

## Testing

- `ocr_service`: `pdf_is_scanned` for text vs no-text PDFs; `_ocr_tesseract`
  with `pytesseract.image_to_string` mocked; `_ocr_vision` with `llm_router`
  mocked; `rasterize_pdf` page count on a minimal synthetic PDF (or fitz mocked).
- `extract_text`: a no-text-layer PDF raises `ScannedPdfError`; normal PDF/docx
  paths do not regress.
- `upload_document` endpoint: scanned + OCR enabled → 202 + a `processing`
  Document + `ocr_ingest_task.delay` called (mocked); scanned + OCR disabled →
  400. Uses the repo's "call the function directly + mock" pattern.
- `ocr_ingest_task`: success → `status="ready"`; OCR raises → `status="failed"`
  with `status_detail`. `ocr_pdf` and `ingest_document` mocked.
- `load_ocr_config`: returns defaults when no row exists.

Real OCR accuracy is not unit-tested; the engines are mocked.

## Operations

- Dockerfile: `apt-get install -y tesseract-ocr tesseract-ocr-chi-sim`.
- `pyproject.toml`: add `pymupdf`, `pytesseract`, `pillow`.
- After pulling: `docker compose build api worker`; migration 016 runs on
  startup (dev) or `alembic upgrade head`.

## Out of scope

- Per-KB / per-upload engine selection.
- Per-page mixed text/scan handling and forced full-document OCR.
- OCR for chat attachments (chat images already go to vision models).
- OCR for non-PDF scanned formats (TIFF, multi-page image archives).
- OCR quality tuning / preprocessing (deskew, denoise).
