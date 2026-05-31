# OCR for Scanned PDFs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OCR scanned/image-only PDFs on knowledge upload — fall back from pypdf to Tesseract (default) or a vision-LLM engine chosen by a global admin setting, running asynchronously on Celery so the single-worker API is never blocked.

**Architecture:** `extract_text()` raises a new `ScannedPdfError` when a PDF has no text layer. The upload endpoint catches it and, if OCR is enabled, creates a `processing` Document and enqueues a Celery `ocr_ingest_task` (raw bytes passed base64). The worker rasterizes pages (PyMuPDF), OCRs them (Tesseract or vision-LLM per `ocr_config`), ingests the text into the existing Document row, and flips its status to `ready`/`failed`. Normal text PDFs keep their synchronous path unchanged.

**Tech Stack:** PyMuPDF (`fitz`) rasterization, `pytesseract` + system Tesseract, optional vision via the existing LLM router, Celery, SQLAlchemy/Alembic, FastAPI, React/TypeScript.

**Design spec:** `docs/superpowers/specs/2026-05-31-ocr-scanned-pdf-design.md`

**Run tests with the project venv:** `python` is not on PATH — use `.venv/bin/python -m pytest`. DB-backed tests need the stack: `docker compose up -d postgres redis`. Alembic head is currently `015_sso_secret_envvar`; this plan adds `016_ocr`.

---

## File Structure

- `pyproject.toml` (modify) — add `pymupdf`, `pytesseract`, `pillow`.
- `Dockerfile` (modify) — install `tesseract-ocr` + `tesseract-ocr-chi-sim`.
- `alembic/versions/016_ocr.py` (create) — `documents.status`/`status_detail` + `ocr_config` table.
- `app/models/knowledge.py` (modify) — add `status`/`status_detail` to `Document`.
- `app/models/ocr.py` (create) — `OcrConfig` single-row model.
- `app/services/ocr_service.py` (create) — `ScannedPdfError`, detection, rasterization, engines, `load_ocr_config`.
- `app/services/knowledge_service.py` (modify) — `extract_text` raises `ScannedPdfError`; `ingest_document` gains `document_id`; add `create_pending_document`.
- `app/workers/tasks.py` (modify) — add `ocr_ingest_task`.
- `app/routers/knowledge.py` (modify) — upload endpoint scanned branch; add `GET/PUT /ocr/config`.
- `app/schemas/` (modify/create) — OCR config request/response schemas.
- `tests/test_ocr_service.py` (create), `tests/test_ocr_ingest.py` (create) — unit tests.
- `webui/src/api/client.ts` (modify) — `getOcrConfig`/`updateOcrConfig`.
- `webui/src/pages/Knowledge.tsx` (modify) — status badges, polling, OCR settings panel.

---

## Task 1: Dependencies and Docker (Tesseract + PyMuPDF)

**Files:**
- Modify: `pyproject.toml`
- Modify: `Dockerfile`

- [ ] **Step 1: Add Python dependencies**

In `pyproject.toml`, in the `dependencies` array (where `"pypdf>=4.0.0",` already lives), add:

```toml
    "pymupdf>=1.24.0",
    "pytesseract>=0.3.10",
    "pillow>=10.0.0",
```

- [ ] **Step 2: Lock and sync**

Run: `uv lock && uv sync`
Expected: lockfile updates; `.venv` gets pymupdf/pytesseract/pillow. (If `uv` is unavailable, use the project's documented install path.)

- [ ] **Step 3: Verify imports work**

Run: `.venv/bin/python -c "import fitz, pytesseract, PIL; print('ok')"`
Expected: prints `ok`. (`pytesseract` imports fine without the system binary; the binary is only needed at OCR time, exercised in Docker.)

- [ ] **Step 4: Install the Tesseract system packages in the image**

In `Dockerfile`, find the existing `apt-get install` layer (or add one before the Python install). Ensure it includes Tesseract and the Simplified-Chinese language pack:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*
```

If the Dockerfile has no apt layer yet, add the block above immediately after the `FROM` line. The same image runs both `api` and `worker` services (see `docker-compose.yml`), so one change covers both.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock Dockerfile
git commit -m "build(ocr): add pymupdf/pytesseract/pillow + tesseract system packages"
```

---

## Task 2: Migration 016 + models (`Document.status`, `OcrConfig`)

**Files:**
- Create: `alembic/versions/016_ocr.py`
- Modify: `app/models/knowledge.py` (add columns to `Document`, around line 69)
- Create: `app/models/ocr.py`

- [ ] **Step 1: Add `status`/`status_detail` to the `Document` model**

In `app/models/knowledge.py`, in `class Document`, after the `metadata_json` column (line 69) add:

```python
    status = Column(String(20), nullable=False, default="ready")  # ready | processing | failed
    status_detail = Column(Text, nullable=True)  # failure reason when status == "failed"
```

`Column`, `String`, `Text` are already imported at the top of the file.

- [ ] **Step 2: Create the `OcrConfig` model**

Create `app/models/ocr.py`:

```python
"""Global OCR configuration (single row)."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class OcrConfig(Base):
    """Single-row global OCR settings (mirrors SsoConfig)."""

    __tablename__ = "ocr_config"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    engine = Column(String(20), nullable=False, default="tesseract")  # tesseract | vision
    vision_provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    vision_model = Column(String(255), nullable=True)
    languages = Column(String(64), nullable=False, default="chi_sim+eng")
    max_pages = Column(Integer, nullable=False, default=30)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

> Confirm the providers table name is `providers` (check `app/models/` for the AI provider model's `__tablename__`); if it differs, use the correct name in the FK.

- [ ] **Step 3: Ensure both models are imported where the metadata is registered**

Models must be imported so Alembic autogenerate/`Base.metadata` sees them and the app can use them. Check how existing models (e.g. `app/models/sso.py`) are exposed in `app/models/__init__.py` and add `OcrConfig` the same way (e.g. `from app.models.ocr import OcrConfig`).

- [ ] **Step 4: Write the migration**

Create `alembic/versions/016_ocr.py`:

```python
"""ocr: documents.status + ocr_config table

Revision ID: 016_ocr
Revises: 015_sso_secret_envvar
"""
import sqlalchemy as sa
from alembic import op

revision = "016_ocr"
down_revision = "015_sso_secret_envvar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
    )
    op.add_column(
        "documents",
        sa.Column("status_detail", sa.Text(), nullable=True),
    )

    op.create_table(
        "ocr_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("engine", sa.String(length=20), nullable=False, server_default="tesseract"),
        sa.Column("vision_provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=True),
        sa.Column("vision_model", sa.String(length=255), nullable=True),
        sa.Column("languages", sa.String(length=64), nullable=False, server_default="chi_sim+eng"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ocr_config")
    op.drop_column("documents", "status_detail")
    op.drop_column("documents", "status")
```

- [ ] **Step 5: Apply the migration and verify head**

Run:
```bash
docker compose up -d postgres
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic current
```
Expected: `alembic current` shows `016_ocr (head)`. The `documents` table has `status`/`status_detail`; `ocr_config` exists.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/016_ocr.py app/models/knowledge.py app/models/ocr.py app/models/__init__.py
git commit -m "feat(ocr): migration 016 — documents.status + ocr_config table"
```

---

## Task 3: `ocr_service.py` — detection, rasterization, engines

**Files:**
- Create: `app/services/ocr_service.py`
- Test: `tests/test_ocr_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ocr_service.py`:

```python
import io
import pytest


def _one_page_text_pdf() -> bytes:
    """A 1-page PDF with a real text layer, built via pypdf+reportlab-free fitz."""
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ocr_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.ocr_service`).

- [ ] **Step 3: Implement `ocr_service.py`**

Create `app/services/ocr_service.py`:

```python
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
```

> The vision message uses the OpenAI multimodal `content` array shape. Verify the project's `llm_router.chat` forwards a list-typed `content` to the provider unchanged (it builds OpenAI-compatible payloads). If it coerces content to a string, adapt to the router's documented multimodal entry point.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ocr_service.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/ocr_service.py tests/test_ocr_service.py
git commit -m "feat(ocr): ocr_service — detection, rasterization, tesseract/vision engines"
```

---

## Task 4: `extract_text` raises `ScannedPdfError`; `load_ocr_config` service

**Files:**
- Modify: `app/services/knowledge_service.py` (line 58-59; add import)
- Modify: `app/services/ocr_service.py` (add `load_ocr_config`)
- Test: `tests/test_ocr_service.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ocr_service.py`:

```python
def test_extract_text_raises_scanned_for_blank_pdf():
    from app.services.knowledge_service import extract_text
    from app.services.ocr_service import ScannedPdfError
    with pytest.raises(ScannedPdfError):
        extract_text(_one_page_blank_pdf(), "application/pdf", "scan.pdf")


def test_extract_text_ok_for_text_pdf():
    from app.services.knowledge_service import extract_text
    out = extract_text(_one_page_text_pdf(), "application/pdf", "doc.pdf")
    assert "Hello text layer" in out


@pytest.mark.asyncio
async def test_load_ocr_config_defaults_when_no_row(monkeypatch):
    import app.services.ocr_service as ocr

    class _NoRowSession:
        async def execute(self, *a, **k):
            class _R:
                def scalar_one_or_none(self_inner): return None
            return _R()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(ocr, "AsyncSessionLocal", lambda: _NoRowSession())
    cfg = await ocr.load_ocr_config()
    assert cfg.enabled is True
    assert cfg.engine == "tesseract"
    assert cfg.languages == "chi_sim+eng"
    assert cfg.max_pages == 30
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ocr_service.py -k "scanned or text_pdf or load_ocr_config" -v`
Expected: FAIL — `extract_text` currently raises plain `ValueError` (not `ScannedPdfError`), and `load_ocr_config` does not exist.

- [ ] **Step 3: Change the `extract_text` empty-PDF branch**

In `app/services/knowledge_service.py`, add an import near the top (with the other imports):

```python
from app.services.ocr_service import ScannedPdfError
```

Then replace line 58-59:

```python
            if not text_out:
                raise ValueError("PDF contains no extractable text (likely scanned image).")
```

with:

```python
            if not text_out:
                raise ScannedPdfError("PDF contains no extractable text (likely scanned image).")
```

Because `ScannedPdfError` subclasses `ValueError`, the surrounding `except ValueError: raise` (line 61-62) still re-raises it unchanged, and any existing caller catching `ValueError` is unaffected.

> Watch for a circular import: `ocr_service` imports `get_llm_router` from `app.services.llm_router`, and `knowledge_service` will import `ScannedPdfError` from `ocr_service`. If `ocr_service` (transitively) imports `knowledge_service`, move `ScannedPdfError` to a tiny `app/services/ocr_errors.py` and import it in both. Verify after the change with `.venv/bin/python -c "import app.services.knowledge_service"`.

- [ ] **Step 4: Add `load_ocr_config` to `ocr_service.py`**

Append to `app/services/ocr_service.py`:

```python
from app.core.database import AsyncSessionLocal  # add near the other imports


async def load_ocr_config() -> OcrSettings:
    """Return the single ocr_config row as OcrSettings, or defaults if none."""
    from sqlalchemy import select
    from app.models.ocr import OcrConfig

    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(OcrConfig))).scalar_one_or_none()
    if row is None:
        return OcrSettings(enabled=True, engine="tesseract", languages="chi_sim+eng",
                           max_pages=30, vision_provider_id=None, vision_model=None)
    return OcrSettings(
        enabled=row.enabled, engine=row.engine, languages=row.languages,
        max_pages=row.max_pages, vision_provider_id=row.vision_provider_id,
        vision_model=row.vision_model,
    )
```

(Keep imports at the top of the file per the existing style; the inline `from ... import` here mirrors the codebase's lazy-import habit to avoid load-order issues — consolidate if the file's convention differs.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ocr_service.py -v`
Expected: PASS (all from Task 3 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add app/services/knowledge_service.py app/services/ocr_service.py tests/test_ocr_service.py
git commit -m "feat(ocr): extract_text raises ScannedPdfError; add load_ocr_config"
```

---

## Task 5: `ingest_document(document_id=...)` + `create_pending_document`

**Files:**
- Modify: `app/services/knowledge_service.py` (`ingest_document` lines 163-244; add `create_pending_document`)
- Test: `tests/test_ocr_ingest.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_ocr_ingest.py`. These need the DB (a real KB + provider for embeddings is heavy), so mock `_embed` to return fixed-dim vectors and use a real session. Follow the `parent_conv_and_internal_agent` fixture style (unique names, cleanup) from `tests/test_internal_agent.py`.

```python
import uuid
import pytest
from unittest.mock import AsyncMock

from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeBase, Document
from app.services.knowledge_service import get_knowledge_service


@pytest.mark.asyncio
async def test_create_pending_document_sets_processing():
    svc = get_knowledge_service()
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        kb = KnowledgeBase(name=f"kb_{uid}", embedding_dim=1536, embedding_model="text-embedding-3-small")
        db.add(kb); await db.commit(); await db.refresh(kb)

        doc = await svc.create_pending_document(
            db=db, kb_id=kb.id, filename="scan.pdf",
            mime_type="application/pdf", raw=b"%PDF-1.4 fake")
        assert doc.status == "processing"
        assert doc.id is not None

        # cleanup
        await db.execute(Document.__table__.delete().where(Document.id == doc.id))
        await db.execute(KnowledgeBase.__table__.delete().where(KnowledgeBase.id == kb.id))
        await db.commit()


@pytest.mark.asyncio
async def test_ingest_into_existing_document_id(monkeypatch):
    svc = get_knowledge_service()
    monkeypatch.setattr(svc, "_embed", AsyncMock(return_value=[[0.1] * 1536]))
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        kb = KnowledgeBase(name=f"kb_{uid}", embedding_dim=1536, embedding_model="text-embedding-3-small")
        db.add(kb); await db.commit(); await db.refresh(kb)
        doc = await svc.create_pending_document(
            db=db, kb_id=kb.id, filename="scan.pdf",
            mime_type="application/pdf", raw=b"%PDF fake")

        result = await svc.ingest_document(
            db=db, kb_id=kb.id, filename="scan.pdf",
            content="recognized text from ocr", mime_type="application/pdf",
            document_id=doc.id)
        assert result.id == doc.id          # reused the same row, no new Document
        await db.refresh(result)
        assert (result.metadata_json or {}).get("chunk_count", 0) >= 1

        await db.execute(Document.__table__.delete().where(Document.id == doc.id))
        await db.execute(KnowledgeBase.__table__.delete().where(KnowledgeBase.id == kb.id))
        await db.commit()
```

> Check `KnowledgeBase`'s required columns before constructing it (the fixture above assumes `name`, `embedding_dim`, `embedding_model`). Adjust to the actual non-nullable fields.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ocr_ingest.py -v`
Expected: FAIL (`create_pending_document` missing; `ingest_document` has no `document_id`).

- [ ] **Step 3: Add `create_pending_document` and a `document_id` branch to `ingest_document`**

In `app/services/knowledge_service.py`, add this method to the service class (near `ingest_document`):

```python
    async def create_pending_document(
        self, db: AsyncSession, kb_id: int, filename: str,
        mime_type: Optional[str], raw: bytes,
    ) -> Document:
        """Insert a Document in 'processing' state (no chunks yet) for async OCR."""
        import hashlib
        doc = Document(
            kb_id=kb_id,
            filename=filename,
            file_hash=hashlib.sha256(raw).hexdigest(),
            file_size=len(raw),
            mime_type=mime_type,
            metadata_json={"filename": filename},
            status="processing",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc
```

Then change `ingest_document` to accept and use `document_id`. Update the signature (line 163-171) to add the parameter:

```python
    async def ingest_document(
        self,
        db: AsyncSession,
        kb_id: int,
        filename: str,
        content: str,
        mime_type: Optional[str] = None,
        provider_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Document:
```

Replace the Document-creation block (lines 216-226) with a branch that reuses an existing row when `document_id` is given:

```python
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if document_id is not None:
            doc = await db.get(Document, document_id)
            if doc is None:
                raise ValueError(f"Document {document_id} not found")
            doc.file_hash = file_hash
            doc.file_size = len(content.encode("utf-8"))
            doc.mime_type = mime_type
            doc.metadata_json = {"chunk_count": len(chunks), "embedding_dim": kb.embedding_dim}
            doc.status = "ready"
            doc.status_detail = None
        else:
            doc = Document(
                kb_id=kb_id,
                filename=filename,
                content_chunks_json=None,
                file_hash=file_hash,
                file_size=len(content.encode("utf-8")),
                mime_type=mime_type,
                metadata_json={"chunk_count": len(chunks), "embedding_dim": kb.embedding_dim},
                status="ready",
            )
            db.add(doc)
        await db.flush()  # ensure doc.id is available
```

The rest of `ingest_document` (chunk records using `doc.id`, `db.add_all`, `db.commit`, `db.refresh`) is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ocr_ingest.py -v`
Expected: PASS (2 tests). Also run `.venv/bin/python -m pytest tests/ -k knowledge -v` if such tests exist, to confirm the existing-row branch didn't regress the default path.

- [ ] **Step 5: Commit**

```bash
git add app/services/knowledge_service.py tests/test_ocr_ingest.py
git commit -m "feat(ocr): ingest_document(document_id) reuse + create_pending_document"
```

---

## Task 6: Celery `ocr_ingest_task`

**Files:**
- Modify: `app/workers/tasks.py` (add task; mirror the `new_event_loop().run_until_complete()` pattern at lines 358-372)
- Test: `tests/test_ocr_ingest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ocr_ingest.py`. The task runs OCR + ingest; mock both so no engine/embedding is needed, and assert the Document's final status.

```python
@pytest.mark.asyncio
async def test_ocr_ingest_task_sets_ready(monkeypatch):
    import app.workers.tasks as tasks
    import app.services.ocr_service as ocr
    svc = get_knowledge_service()

    monkeypatch.setattr(ocr, "ocr_pdf", AsyncMock(return_value="ocr text out"))
    monkeypatch.setattr(svc, "_embed", AsyncMock(return_value=[[0.2] * 1536]))

    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        kb = KnowledgeBase(name=f"kb_{uid}", embedding_dim=1536, embedding_model="text-embedding-3-small")
        db.add(kb); await db.commit(); await db.refresh(kb)
        doc = await svc.create_pending_document(
            db=db, kb_id=kb.id, filename="s.pdf", mime_type="application/pdf", raw=b"%PDF x")
        kb_id, doc_id = kb.id, doc.id

    import base64
    tasks.ocr_ingest_task(doc_id, kb_id, base64.b64encode(b"%PDF x").decode(), "s.pdf", "application/pdf")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Document, doc_id)
        assert refreshed.status == "ready"
        await db.execute(Document.__table__.delete().where(Document.id == doc_id))
        await db.execute(KnowledgeBase.__table__.delete().where(KnowledgeBase.id == kb_id))
        await db.commit()


@pytest.mark.asyncio
async def test_ocr_ingest_task_sets_failed_on_error(monkeypatch):
    import app.workers.tasks as tasks
    import app.services.ocr_service as ocr
    svc = get_knowledge_service()

    monkeypatch.setattr(ocr, "ocr_pdf", AsyncMock(side_effect=RuntimeError("engine down")))

    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        kb = KnowledgeBase(name=f"kb_{uid}", embedding_dim=1536, embedding_model="text-embedding-3-small")
        db.add(kb); await db.commit(); await db.refresh(kb)
        doc = await svc.create_pending_document(
            db=db, kb_id=kb.id, filename="s.pdf", mime_type="application/pdf", raw=b"%PDF x")
        kb_id, doc_id = kb.id, doc.id

    import base64
    tasks.ocr_ingest_task(doc_id, kb_id, base64.b64encode(b"%PDF x").decode(), "s.pdf", "application/pdf")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Document, doc_id)
        assert refreshed.status == "failed"
        assert "engine down" in (refreshed.status_detail or "")
        await db.execute(Document.__table__.delete().where(Document.id == doc_id))
        await db.execute(KnowledgeBase.__table__.delete().where(KnowledgeBase.id == kb_id))
        await db.commit()
```

> Note: `ocr_ingest_task` is called directly (not via `.delay`) so it runs synchronously in-process. The task body must reference `ocr_pdf` via the `ocr` module (e.g. `from app.services import ocr_service` then `ocr_service.ocr_pdf(...)`) so the monkeypatch takes effect.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ocr_ingest.py -k ocr_ingest_task -v`
Expected: FAIL (`ocr_ingest_task` does not exist).

- [ ] **Step 3: Implement the task**

In `app/workers/tasks.py`, add (mirroring the existing `new_event_loop()` pattern). Use `@celery_app.task(bind=True, max_retries=1)` to match the file's other tasks:

```python
@celery_app.task(bind=True, max_retries=1)
def ocr_ingest_task(self, document_id, kb_id, raw_b64, filename, mime_type):
    """OCR a scanned PDF and ingest it into an existing (processing) Document row."""
    import asyncio
    import base64
    from sqlalchemy import update
    from app.core.database import AsyncSessionLocal
    from app.models.knowledge import Document
    from app.services import ocr_service
    from app.services.knowledge_service import get_knowledge_service

    raw = base64.b64decode(raw_b64)

    async def _run():
        try:
            cfg = await ocr_service.load_ocr_config()
            text = await ocr_service.ocr_pdf(raw, cfg)
            if not text.strip():
                raise ValueError("OCR 未识别出文字")
            async with AsyncSessionLocal() as db:
                await get_knowledge_service().ingest_document(
                    db=db, kb_id=kb_id, filename=filename, content=text,
                    mime_type=mime_type, document_id=document_id)
            # ingest_document already set status="ready" on the row
        except Exception as e:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Document).where(Document.id == document_id)
                    .values(status="failed", status_detail=str(e)[:500]))
                await db.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ocr_ingest.py -k ocr_ingest_task -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/workers/tasks.py tests/test_ocr_ingest.py
git commit -m "feat(ocr): ocr_ingest_task — OCR + ingest into processing doc, set status"
```

---

## Task 7: Upload endpoint scanned branch (202) + OCR settings endpoints

**Files:**
- Modify: `app/routers/knowledge.py` (upload endpoint lines 142-170; add `GET/PUT /ocr/config`)
- Modify/Create: `app/schemas/` (OCR config schema)
- Test: `tests/test_ocr_endpoint.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_ocr_endpoint.py`. Follow the repo's "call the router function directly + mock" style (see `tests/test_gateway_manifest.py`).

```python
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
    delay = patch("app.workers.tasks.ocr_ingest_task.delay")

    class _F:
        filename = "scan.pdf"; content_type = "application/pdf"
        async def read(self): return b"%PDF scan"

    with delay as mock_delay:
        resp = await kn.upload_document(kb_id=1, file=_F(), provider_id=None,
                                        db=AsyncMock(), _=None)
    # 202 body carries the processing document
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_ocr_endpoint.py -v`
Expected: FAIL (endpoint still raises 400 generically on `ValueError`; no scanned branch; `load_ocr_config` not imported into the router).

- [ ] **Step 3: Update the upload endpoint**

In `app/routers/knowledge.py`, add imports near the top:

```python
import base64
from fastapi.responses import JSONResponse
from app.services.ocr_service import ScannedPdfError, load_ocr_config
```

Add a module-level constant:

```python
MAX_OCR_BYTES = 20 * 1024 * 1024  # 20 MB
```

Replace the `try/except ValueError` extraction block (lines 143-146) and keep the rest, so the body becomes:

```python
    raw = await file.read()
    try:
        content = extract_text(raw, file.content_type, file.filename or "")
    except ScannedPdfError:
        cfg = await load_ocr_config()
        if not cfg.enabled:
            raise HTTPException(status_code=400, detail="扫描件 PDF 需启用 OCR（请在 OCR 设置中开启）")
        if len(raw) > MAX_OCR_BYTES:
            raise HTTPException(status_code=413, detail="扫描件超出 OCR 大小上限（20MB）")
        from app.workers.tasks import ocr_ingest_task
        service = get_knowledge_service()
        doc = await service.create_pending_document(
            db=db, kb_id=kb_id, filename=file.filename,
            mime_type=file.content_type, raw=raw)
        ocr_ingest_task.delay(
            doc.id, kb_id, base64.b64encode(raw).decode(),
            file.filename, file.content_type)
        return JSONResponse(status_code=202,
                            content={"document_id": doc.id, "status": "processing"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

The existing synchronous block below (`service = get_knowledge_service()` … `return DocumentUploadResponse(...)`) is unchanged and only runs when `extract_text` succeeded. Returning a `JSONResponse` directly bypasses the `response_model`, which is intended for the 202 case.

- [ ] **Step 4: Add the OCR settings schema + endpoints**

Create the schema in `app/schemas/ocr.py`:

```python
from typing import Optional
from pydantic import BaseModel


class OcrConfigRead(BaseModel):
    enabled: bool
    engine: str
    vision_provider_id: Optional[int] = None
    vision_model: Optional[str] = None
    languages: str
    max_pages: int


class OcrConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    engine: Optional[str] = None
    vision_provider_id: Optional[int] = None
    vision_model: Optional[str] = None
    languages: Optional[str] = None
    max_pages: Optional[int] = None
```

Add the endpoints in `app/routers/knowledge.py` (ADMIN). Use whatever admin-gate the repo uses for other admin endpoints — check `app/routers/sso.py`'s `/sso/config` (an existing ADMIN single-row config endpoint) and copy its permission dependency exactly:

```python
@router.get("/ocr/config", response_model=OcrConfigRead)
async def get_ocr_config(db: AsyncSession = Depends(get_db),
                         _=Depends(require_permission(Permission.ADMIN))):
    from sqlalchemy import select
    from app.models.ocr import OcrConfig
    row = (await db.execute(select(OcrConfig))).scalar_one_or_none()
    if row is None:
        return OcrConfigRead(enabled=True, engine="tesseract", vision_provider_id=None,
                             vision_model=None, languages="chi_sim+eng", max_pages=30)
    return OcrConfigRead(
        enabled=row.enabled, engine=row.engine, vision_provider_id=row.vision_provider_id,
        vision_model=row.vision_model, languages=row.languages, max_pages=row.max_pages)


@router.put("/ocr/config", response_model=OcrConfigRead)
async def update_ocr_config(body: OcrConfigUpdate, db: AsyncSession = Depends(get_db),
                            _=Depends(require_permission(Permission.ADMIN))):
    from sqlalchemy import select
    from app.models.ocr import OcrConfig
    row = (await db.execute(select(OcrConfig))).scalar_one_or_none()
    if row is None:
        row = OcrConfig()
        db.add(row)
    for field in ("enabled", "engine", "vision_provider_id", "vision_model", "languages", "max_pages"):
        val = getattr(body, field)
        if val is not None:
            setattr(row, field, val)
    await db.commit(); await db.refresh(row)
    return OcrConfigRead(
        enabled=row.enabled, engine=row.engine, vision_provider_id=row.vision_provider_id,
        vision_model=row.vision_model, languages=row.languages, max_pages=row.max_pages)
```

Import `OcrConfigRead`/`OcrConfigUpdate` at the top of the router. Verify the correct admin `Permission` name (e.g. `Permission.ADMIN` vs a specific one) against `app/routers/sso.py`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ocr_endpoint.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add app/routers/knowledge.py app/schemas/ocr.py tests/test_ocr_endpoint.py
git commit -m "feat(ocr): upload scanned branch (202) + GET/PUT /ocr/config"
```

---

## Task 8: Frontend — status badges, polling, OCR settings panel

**Files:**
- Modify: `webui/src/api/client.ts`
- Modify: `webui/src/pages/Knowledge.tsx`

- [ ] **Step 1: Add API client methods**

In `webui/src/api/client.ts`, add to the `api` object (near other config getters):

```typescript
  getOcrConfig: () => request('/ocr/config'),
  updateOcrConfig: (body: {
    enabled?: boolean; engine?: string; vision_provider_id?: number | null;
    vision_model?: string | null; languages?: string; max_pages?: number;
  }) => request('/ocr/config', { method: 'PUT', body: JSON.stringify(body) }),
```

Confirm the document-list fetch the page already uses returns the new `status` / `status_detail` fields (they come from the Document model automatically if the list endpoint serializes the row; if it uses an explicit response schema, add `status`/`status_detail` to that schema in `app/schemas/`).

- [ ] **Step 2: Render status badges in the document list**

In `webui/src/pages/Knowledge.tsx`, where each document row renders, add a badge driven by `doc.status`:

```tsx
{doc.status === 'processing' && (
  <span style={{ fontSize: 11, color: '#f59e0b', letterSpacing: '0.08em' }}>● OCR 识别中…</span>
)}
{doc.status === 'failed' && (
  <span title={doc.status_detail || ''} style={{ fontSize: 11, color: '#f87171', letterSpacing: '0.08em' }}>● 失败</span>
)}
```

(Match the existing document-row markup and styling in the file; `ready` documents show no badge.)

- [ ] **Step 3: Poll while any document is processing**

In the `Knowledge` component, after the documents are loaded into state, add an effect that re-fetches every 5s while any doc is `processing`:

```tsx
useEffect(() => {
  const hasProcessing = documents.some(d => d.status === 'processing')
  if (!hasProcessing) return
  const t = setInterval(() => { reloadDocuments() }, 5000)
  return () => clearInterval(t)
}, [documents])
```

Use the page's actual documents state variable and its reload function names (inspect the file; `documents`/`reloadDocuments` are placeholders for whatever the page already calls).

- [ ] **Step 4: Add the OCR settings panel (admin)**

Add a collapsible "OCR 设置" panel near the top of the Knowledge page. Minimal, consistent with existing panels in the file:

```tsx
function OcrSettingsPanel() {
  const [cfg, setCfg] = useState<any>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { if (open && !cfg) api.getOcrConfig().then(setCfg) }, [open, cfg])
  if (!open) return <button onClick={() => setOpen(true)} style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>OCR 设置 ▾</button>
  if (!cfg) return <div>加载中…</div>
  const save = async () => { await api.updateOcrConfig(cfg); setOpen(false) }
  return (
    <div style={{ border: '1px solid var(--border, #333)', borderRadius: 8, padding: 12, margin: '8px 0' }}>
      <label style={{ display: 'block', marginBottom: 6 }}>
        <input type="checkbox" checked={cfg.enabled} onChange={e => setCfg({ ...cfg, enabled: e.target.checked })} /> 启用 OCR
      </label>
      <label style={{ display: 'block', marginBottom: 6 }}>引擎:
        <select value={cfg.engine} onChange={e => setCfg({ ...cfg, engine: e.target.value })}>
          <option value="tesseract">Tesseract（本地）</option>
          <option value="vision">Vision LLM</option>
        </select>
      </label>
      {cfg.engine === 'vision' && (
        <>
          <label style={{ display: 'block', marginBottom: 6 }}>Vision Provider ID:
            <input type="number" value={cfg.vision_provider_id ?? ''} onChange={e => setCfg({ ...cfg, vision_provider_id: e.target.value ? Number(e.target.value) : null })} />
          </label>
          <label style={{ display: 'block', marginBottom: 6 }}>Vision 模型:
            <input value={cfg.vision_model ?? ''} onChange={e => setCfg({ ...cfg, vision_model: e.target.value })} />
          </label>
        </>
      )}
      <label style={{ display: 'block', marginBottom: 6 }}>语言:
        <input value={cfg.languages} onChange={e => setCfg({ ...cfg, languages: e.target.value })} />
      </label>
      <label style={{ display: 'block', marginBottom: 6 }}>最大页数:
        <input type="number" value={cfg.max_pages} onChange={e => setCfg({ ...cfg, max_pages: Number(e.target.value) })} />
      </label>
      <button onClick={save} style={{ padding: '4px 14px', background: 'var(--accent)', color: '#000', border: 'none', borderRadius: 6, cursor: 'pointer' }}>保存</button>
      <button onClick={() => setOpen(false)} style={{ marginLeft: 8, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>取消</button>
    </div>
  )
}
```

Render `<OcrSettingsPanel />` near the top of the Knowledge page's JSX. (The vision provider could later become a dropdown of configured providers; a numeric ID input keeps this increment minimal.)

- [ ] **Step 5: Type-check and build**

Run: `cd webui && npm run build`
Expected: 0 TypeScript errors. Adjust the `doc.status`/document type if the page's `Document` TS type needs `status`/`status_detail` added.

- [ ] **Step 6: Commit**

```bash
git add webui/src/api/client.ts webui/src/pages/Knowledge.tsx
git commit -m "feat(webui): OCR status badges, polling, and OCR settings panel"
```

---

## Final verification

- [ ] Backend suite with stack up:

```bash
docker compose up -d postgres redis
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest -q
```

Expected: existing suite + new `test_ocr_service.py`, `test_ocr_ingest.py`, `test_ocr_endpoint.py` pass.

- [ ] End-to-end (manual): `docker compose build api worker && docker compose up -d`. Upload a real scanned PDF to a KB → expect a `processing` document that flips to `ready` after the worker OCRs it; query the KB and confirm the OCR'd text is retrievable. Toggle engine to Vision (with a configured vision provider) and repeat.

- [ ] Frontend builds clean: `cd webui && npm run build`.

- [ ] Update `docs/superpowers/plans/project_status.md`: move "OCR for scanned-image PDFs" out of "Not yet implemented"; note alembic head is now `016_ocr`.

- [ ] Use `superpowers:finishing-a-development-branch` to decide merge/PR for `feat/ocr-scanned-pdf`.
