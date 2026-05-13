"""Knowledge base and document management router."""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.knowledge import (
    KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate, KnowledgeBaseListResponse,
    DocumentRead, DocumentListResponse, DocumentTextIngestRequest, DocumentUploadResponse,
    KnowledgeQueryRequest, KnowledgeQueryResponse,
)
from app.models.knowledge import KnowledgeBase, Document
from app.services.knowledge_service import get_knowledge_service, extract_text

router = APIRouter()


# ---------------------------------------------------------------------------
# Knowledge Base CRUD
# ---------------------------------------------------------------------------
@router.get("/knowledge/bases", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_READ))):
    total_result = await db.execute(select(func.count(KnowledgeBase.id)))
    total = total_result.scalar()
    result = await db.execute(select(KnowledgeBase).offset(skip).limit(limit))
    kbs = result.scalars().all()
    return KnowledgeBaseListResponse(total=total, knowledge_bases=[KnowledgeBaseRead.model_validate(k) for k in kbs])


@router.post("/knowledge/bases", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(body: KnowledgeBaseCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_WRITE))):
    existing = await db.execute(select(KnowledgeBase).where(KnowledgeBase.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Knowledge base name already exists")
    kb = KnowledgeBase(**body.model_dump())
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KnowledgeBaseRead.model_validate(kb)


@router.get("/knowledge/bases/{kb_id}", response_model=KnowledgeBaseRead)
async def get_knowledge_base(kb_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_READ))):
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KnowledgeBaseRead.model_validate(kb)


@router.put("/knowledge/bases/{kb_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base(kb_id: int, body: KnowledgeBaseUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_WRITE))):
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(kb, key, value)
    await db.commit()
    await db.refresh(kb)
    return KnowledgeBaseRead.model_validate(kb)


@router.delete("/knowledge/bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(kb_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_WRITE))):
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await db.delete(kb)
    await db.commit()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@router.get("/knowledge/bases/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(kb_id: int, skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_READ))):
    total_result = await db.execute(select(func.count(Document.id)).where(Document.kb_id == kb_id))
    total = total_result.scalar()
    result = await db.execute(
        select(Document).where(Document.kb_id == kb_id).offset(skip).limit(limit).order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return DocumentListResponse(total=total, documents=[DocumentRead.model_validate(d) for d in docs])


@router.post(
    "/knowledge/bases/{kb_id}/documents/text",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_text_document(
    kb_id: int,
    body: DocumentTextIngestRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
):
    """Ingest plain text as a new document (chunk + embed + store)."""
    service = get_knowledge_service()
    try:
        doc = await service.ingest_document(
            db=db,
            kb_id=kb_id,
            filename=body.filename,
            content=body.content,
            mime_type=body.mime_type,
            provider_id=body.provider_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    chunk_count = (doc.metadata_json or {}).get("chunk_count", 0)
    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.filename,
        file_hash=doc.file_hash or "",
        status="ingested",
        chunks_count=chunk_count,
    )


@router.post(
    "/knowledge/bases/{kb_id}/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    provider_id: int | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
):
    """
    Upload a document. Supported formats:
      - PDF (application/pdf) — text extracted via pypdf (scanned-image PDFs not supported)
      - Word (.docx) — text + tables extracted via python-docx
      - UTF-8 text (.txt / .md / .csv / .json / .html / ...) — decoded as-is
    """
    raw = await file.read()
    try:
        content = extract_text(raw, file.content_type, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    service = get_knowledge_service()
    try:
        doc = await service.ingest_document(
            db=db,
            kb_id=kb_id,
            filename=file.filename,
            content=content,
            mime_type=file.content_type,
            provider_id=provider_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    chunk_count = (doc.metadata_json or {}).get("chunk_count", 0)
    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.filename,
        file_hash=doc.file_hash or "",
        status="ingested",
        chunks_count=chunk_count,
    )


@router.delete(
    "/knowledge/bases/{kb_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
):
    """Delete a document from the knowledge base."""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------
@router.post("/knowledge/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(
    body: KnowledgeQueryRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.KNOWLEDGE_READ)),
):
    """
    Embed the query and return the top-k most similar chunks
    from the specified knowledge base.
    """
    service = get_knowledge_service()
    try:
        results = await service.query(
            db=db,
            kb_id=body.kb_id,
            query=body.query,
            top_k=body.top_k,
            similarity_threshold=body.similarity_threshold,
            provider_id=body.provider_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        return KnowledgeQueryResponse(
            kb_id=body.kb_id,
            query=body.query,
            total=0,
            results=[],
            message=f"Query failed: {e}. Check that an AI Provider with embedding support is configured.",
        )

    return KnowledgeQueryResponse(
        kb_id=body.kb_id,
        query=body.query,
        total=len(results),
        results=results,
    )
