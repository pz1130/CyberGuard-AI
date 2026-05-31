import uuid
import asyncio as _aio
import pytest
from unittest.mock import AsyncMock

from app.core.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeBase, Document
from app.services.knowledge_service import get_knowledge_service


async def _call_task(fn, *args):
    """Run a sync Celery task body (which spins its own event loop) off the
    test's event loop, in a worker thread, so the loops don't collide."""
    await _aio.to_thread(fn, *args)


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
        assert result.id == doc.id
        await db.refresh(result)
        assert (result.metadata_json or {}).get("chunk_count", 0) >= 1

        await db.execute(Document.__table__.delete().where(Document.id == doc.id))
        await db.execute(KnowledgeBase.__table__.delete().where(KnowledgeBase.id == kb.id))
        await db.commit()


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
    await _call_task(tasks.ocr_ingest_task, doc_id, kb_id,
                     base64.b64encode(b"%PDF x").decode(), "s.pdf", "application/pdf")

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
    await _call_task(tasks.ocr_ingest_task, doc_id, kb_id,
                     base64.b64encode(b"%PDF x").decode(), "s.pdf", "application/pdf")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Document, doc_id)
        assert refreshed.status == "failed"
        assert "engine down" in (refreshed.status_detail or "")
        await db.execute(Document.__table__.delete().where(Document.id == doc_id))
        await db.execute(KnowledgeBase.__table__.delete().where(KnowledgeBase.id == kb_id))
        await db.commit()
