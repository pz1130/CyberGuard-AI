# Chat Attachment Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chat attachments (text, PDF, images) meaningful to the agent by extracting their text — reusing existing extraction/OCR toolkits — instead of base64→UTF-8 garbage truncated to 1000 chars.

**Architecture:** A new `attachment_extractor` module converts each attachment to text (text decode / pypdf / OCR fallback / image OCR), with configurable per-attachment and total char caps. A thin `ocr_image` wrapper is added to `ocr_service`. The Celery worker delegates attachment processing to the new module inside its existing event loop.

**Tech Stack:** Python, FastAPI/Celery, `pypdf` (text PDFs), `ocr_service` (Tesseract/vision OCR), pytest (`asyncio_mode = "auto"`, but tests keep the `@pytest.mark.asyncio` convention used in `tests/test_ocr_service.py`).

**Spec:** `docs/superpowers/specs/2026-06-02-chat-attachment-extraction-design.md`
**Issue:** [#13](https://github.com/pz1130/CyberGuard-AI/issues/13)

---

## File Structure

- **Create** `app/services/attachment_extractor.py` — per-file extraction (`extract_attachment_text`), the orchestration that decodes attachment dicts + caps + formats (`build_attachment_section`), and a pure cap helper (`cap_text`).
- **Modify** `app/services/ocr_service.py` — add public `ocr_image(raw, cfg)` wrapper.
- **Modify** `app/config.py` — add `ATTACHMENT_MAX_CHARS`, `ATTACHMENT_TOTAL_MAX_CHARS`.
- **Modify** `app/workers/tasks.py:336-356` — replace the base64→UTF-8 block with an awaited call to `build_attachment_section` inside `_run`.
- **Create** `tests/test_attachment_extractor.py` — unit + integration tests for the new module.
- **Modify** `tests/test_ocr_service.py` — tests for `ocr_image`.

**Branch:** create `feat/chat-attachment-extraction` off `main` before Task 1 (do NOT commit to `main`). Open a PR at the end.

---

### Task 0: Create feature branch

- [ ] **Step 1: Branch off main**

```bash
git checkout main && git pull --ff-only origin main
git checkout -b feat/chat-attachment-extraction
```

---

### Task 1: `ocr_image` wrapper in `ocr_service`

**Files:**
- Modify: `app/services/ocr_service.py` (add `ocr_image` after `ocr_pdf`, ~line 74)
- Test: `tests/test_ocr_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ocr_service.py`:

```python
@pytest.mark.asyncio
async def test_ocr_image_uses_tesseract(monkeypatch):
    import app.services.ocr_service as ocr
    seen = {}

    async def fake_tess(images, languages):
        seen["images"] = images
        seen["languages"] = languages
        return "TESS"

    monkeypatch.setattr(ocr, "_ocr_tesseract", fake_tess)
    cfg = ocr.OcrSettings(enabled=True, engine="tesseract", languages="eng",
                          max_pages=5, vision_provider_id=None, vision_model=None)
    out = await ocr.ocr_image(b"IMGBYTES", cfg)
    assert out == "TESS"
    assert seen["images"] == [b"IMGBYTES"]
    assert seen["languages"] == "eng"


@pytest.mark.asyncio
async def test_ocr_image_uses_vision(monkeypatch):
    import app.services.ocr_service as ocr
    seen = {}

    async def fake_vision(images, provider_id, model):
        seen["images"] = images
        seen["provider_id"] = provider_id
        seen["model"] = model
        return "VIS"

    monkeypatch.setattr(ocr, "_ocr_vision", fake_vision)
    cfg = ocr.OcrSettings(enabled=True, engine="vision", languages="eng",
                          max_pages=5, vision_provider_id=7, vision_model="gpt-4o")
    out = await ocr.ocr_image(b"IMGBYTES", cfg)
    assert out == "VIS"
    assert seen["images"] == [b"IMGBYTES"]
    assert seen["provider_id"] == 7
    assert seen["model"] == "gpt-4o"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ocr_service.py -k ocr_image -v`
Expected: FAIL — `AttributeError: module 'app.services.ocr_service' has no attribute 'ocr_image'`

- [ ] **Step 3: Implement `ocr_image`**

In `app/services/ocr_service.py`, immediately after the `ocr_pdf` function (ends ~line 73), add:

```python
async def ocr_image(raw: bytes, cfg: OcrSettings) -> str:
    """OCR a single image (Tesseract or vision, per cfg.engine).

    Unlike ocr_pdf there is no rasterization step — the payload is already an
    image, so it is passed through as a single-element list. PIL/Tesseract and
    the vision data-URL both accept png/jpeg/gif/webp.
    """
    if cfg.engine == "vision" and cfg.vision_provider_id:
        return await _ocr_vision([raw], cfg.vision_provider_id, cfg.vision_model)
    return await _ocr_tesseract([raw], cfg.languages)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ocr_service.py -k ocr_image -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/ocr_service.py tests/test_ocr_service.py
git commit -m "feat(ocr): add ocr_image wrapper for single-image OCR (#13)"
```

---

### Task 2: `extract_attachment_text` — per-file routing

**Files:**
- Create: `app/services/attachment_extractor.py`
- Test: `tests/test_attachment_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_attachment_extractor.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_attachment_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.attachment_extractor'`

- [ ] **Step 3: Implement `extract_attachment_text`**

Create `app/services/attachment_extractor.py`:

```python
"""Extract plain text from chat attachments for injection into the agent prompt.

Reuses knowledge_service.extract_text (pypdf / docx / utf-8) and ocr_service
(scanned-PDF + image OCR). Every branch degrades to a marker string on failure
so one bad attachment never aborts an agent run. See
docs/superpowers/specs/2026-06-02-chat-attachment-extraction-design.md
"""
from __future__ import annotations

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
                return extract_text(raw, content_type, filename)
            except ScannedPdfError:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_attachment_extractor.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/attachment_extractor.py tests/test_attachment_extractor.py
git commit -m "feat(attachments): per-file text extraction with OCR fallback (#13)"
```

---

### Task 3: `cap_text` + `build_attachment_section` orchestration

**Files:**
- Modify: `app/services/attachment_extractor.py`
- Test: `tests/test_attachment_extractor.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_attachment_extractor.py`:

```python
def test_cap_text_under_limit_unchanged():
    assert ax.cap_text("short", 100) == "short"


def test_cap_text_over_limit_truncates_with_marker():
    out = ax.cap_text("abcdefghij", 4)
    assert out.startswith("abcd")
    assert "...[truncated 6 chars]" in out


@pytest.mark.asyncio
async def test_build_section_empty_when_no_attachments():
    out = await ax.build_attachment_section([], _cfg(), per_cap=8000, total_cap=24000)
    assert out == ""


@pytest.mark.asyncio
async def test_build_section_formats_and_decodes(monkeypatch):
    # Real extraction path for a text/plain file (no mocks): exercises base64
    # decode -> extract -> format end to end (the worker's behavior).
    import base64
    data = base64.b64encode("file body".encode()).decode()
    atts = [{"filename": "n.txt", "content_type": "text/plain", "data": data}]
    out = await ax.build_attachment_section(atts, _cfg(), per_cap=8000, total_cap=24000)
    assert out.startswith("\n\n--- 附件信息 ---\n")
    assert "[附件: n.txt] (type: text/plain)" in out
    assert "file body" in out


@pytest.mark.asyncio
async def test_build_section_applies_per_attachment_cap(monkeypatch):
    async def fake_extract(raw, ct, fn, cfg):
        return "x" * 50
    monkeypatch.setattr(ax, "extract_attachment_text", fake_extract)
    atts = [{"filename": "n.txt", "content_type": "text/plain", "data": ""}]
    out = await ax.build_attachment_section(atts, _cfg(), per_cap=10, total_cap=24000)
    assert "...[truncated 40 chars]" in out


@pytest.mark.asyncio
async def test_build_section_applies_total_cap(monkeypatch):
    async def fake_extract(raw, ct, fn, cfg):
        return "y" * 100
    monkeypatch.setattr(ax, "extract_attachment_text", fake_extract)
    atts = [
        {"filename": "a.txt", "content_type": "text/plain", "data": ""},
        {"filename": "b.txt", "content_type": "text/plain", "data": ""},
    ]
    out = await ax.build_attachment_section(atts, _cfg(), per_cap=8000, total_cap=50)
    assert "...[truncated" in out


@pytest.mark.asyncio
async def test_build_section_bad_base64_yields_marker(monkeypatch):
    atts = [{"filename": "n.bin", "content_type": "text/plain", "data": "!!!notb64!!!"}]
    out = await ax.build_attachment_section(atts, _cfg(), per_cap=8000, total_cap=24000)
    # Decode failure is caught and surfaced as a per-file marker, not a crash.
    assert "[附件: n.bin]" in out
    assert "提取失败" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_attachment_extractor.py -k "cap_text or build_section" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'cap_text'`

- [ ] **Step 3: Implement `cap_text` and `build_attachment_section`**

Add to `app/services/attachment_extractor.py` (after `extract_attachment_text`, and add `import base64` to the imports at top):

```python
import base64
```

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_attachment_extractor.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add app/services/attachment_extractor.py tests/test_attachment_extractor.py
git commit -m "feat(attachments): build_attachment_section with per/total caps (#13)"
```

---

### Task 4: Config settings for caps

**Files:**
- Modify: `app/config.py` (near `MOCK_MODE`, ~line 59)
- Test: `tests/test_attachment_extractor.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_attachment_extractor.py`:

```python
def test_config_has_attachment_caps():
    from app.config import settings
    assert settings.ATTACHMENT_MAX_CHARS == 8000
    assert settings.ATTACHMENT_TOTAL_MAX_CHARS == 24000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_attachment_extractor.py -k config_has_attachment_caps -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'ATTACHMENT_MAX_CHARS'`

- [ ] **Step 3: Add the settings**

In `app/config.py`, after the `MOCK_MODE` line (`MOCK_MODE: bool = False`), add:

```python
    # Chat attachment extraction caps (chars)
    ATTACHMENT_MAX_CHARS: int = 8000          # per attachment
    ATTACHMENT_TOTAL_MAX_CHARS: int = 24000   # across all attachments in one request
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_attachment_extractor.py -k config_has_attachment_caps -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_attachment_extractor.py
git commit -m "feat(config): add ATTACHMENT_MAX_CHARS / ATTACHMENT_TOTAL_MAX_CHARS (#13)"
```

---

### Task 5: Wire the worker to the new extractor

**Files:**
- Modify: `app/workers/tasks.py:336-374` (replace the sync base64→utf-8 block; move attachment processing into `_run`)

- [ ] **Step 1: Replace the attachment block**

In `app/workers/tasks.py`, delete the current block (lines 336-356):

```python
    # Inject attachment content into user_input when attachments are present
    attachments = kwargs.get("attachments")
    if attachments:
        attachment_lines = []
        for att in attachments:
            filename = att.get("filename", "attachment")
            # Router stores base64 content under "data" key
            b64_content = att.get("data", "")
            mime_type = att.get("content_type", "")
            # Decode base64 to get text content
            try:
                import base64 as b64_mod
                content = b64_mod.b64decode(b64_content).decode("utf-8", errors="replace")
            except Exception:
                content = ""
            # Truncate very long content
            truncated = content[:1000] if content else ""
            attachment_lines.append(f"[附件: {filename}] (type: {mime_type})\n{truncated}")

        attachment_desc = "\n\n".join(attachment_lines)
        user_input = f"{user_input}\n\n--- 附件信息 ---\n{attachment_desc}"

    async def _run():
        master_agent = get_master_agent()
        return await master_agent.run(
            user_input=user_input,
            user_id=user_id,
            conversation_history=conversation_history,
            **{**kwargs, **conv_overrides},
        )
```

Replace it with (attachment processing now happens async inside `_run`):

```python
    async def _run():
        run_input = user_input
        attachments = kwargs.get("attachments")
        if attachments:
            from app.config import settings
            from app.services.attachment_extractor import build_attachment_section
            from app.services.ocr_service import load_ocr_config
            cfg = await load_ocr_config()
            section = await build_attachment_section(
                attachments, cfg,
                per_cap=settings.ATTACHMENT_MAX_CHARS,
                total_cap=settings.ATTACHMENT_TOTAL_MAX_CHARS,
            )
            run_input = f"{run_input}{section}"

        master_agent = get_master_agent()
        return await master_agent.run(
            user_input=run_input,
            user_id=user_id,
            conversation_history=conversation_history,
            **{**kwargs, **conv_overrides},
        )
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `python -c "import app.workers.tasks"`
Expected: no output, exit 0 (no ImportError / SyntaxError)

- [ ] **Step 3: Run the full extractor + ocr test suites**

Run: `python -m pytest tests/test_attachment_extractor.py tests/test_ocr_service.py -v`
Expected: PASS (all). `build_attachment_section` is the exact function the worker calls, so `test_build_section_formats_and_decodes` is the end-to-end integration assertion for the worker's attachment behavior.

- [ ] **Step 4: Commit**

```bash
git add app/workers/tasks.py
git commit -m "feat(worker): extract attachment text via attachment_extractor (#13)

Replaces base64->utf-8 truncated-to-1000 handling with real text/PDF/image
extraction (OCR fallback) and configurable caps. Resolves #13."
```

---

### Task 6: Final verification + PR

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/test_attachment_extractor.py tests/test_ocr_service.py -v`
Expected: all pass. (Optionally run the broader suite per the DB recipe in memory if touching DB-backed paths — not required here.)

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin feat/chat-attachment-extraction
gh pr create --title "feat: meaningful chat attachments (text/PDF/image extraction) (#13)" \
  --body "Implements the design in docs/superpowers/specs/2026-06-02-chat-attachment-extraction-design.md. Closes #13."
```

---

## Self-Review

**Spec coverage:**
- Extract-to-text routing (text / PDF / scanned-PDF fallback / image) → Task 2. ✓
- `ocr_image` wrapper → Task 1. ✓
- Worker integration inside event loop → Task 5. ✓
- Configurable per-attachment + total caps with truncation marker → Tasks 3 + 4. ✓
- Per-file failure markers + OCR-disabled marker → Tasks 2 + 3. ✓
- Testing (each routing branch, capping, OCR-disabled, failure, worker integration) → Tasks 1-3, 5. ✓
- Out of scope items (multimodal, summarization, new types) → not implemented. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✓

**Type consistency:** `extract_attachment_text(raw, content_type, filename, cfg)`, `cap_text(text, limit)`, `build_attachment_section(attachments, cfg, *, per_cap, total_cap)`, `ocr_image(raw, cfg)` — names/signatures identical across tasks and the worker call. `OcrSettings` constructed by keyword (it is a `@dataclass`). `ScannedPdfError`/`extract_text` imported from their real modules (`ocr_service` / `knowledge_service`). ✓
