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
