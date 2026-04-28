"""Knowledge base and document management router."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.knowledge import (
    KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate, KnowledgeBaseListResponse,
    DocumentRead, DocumentListResponse,
    KnowledgeQueryRequest, KnowledgeQueryResponse,
)
from app.models.knowledge import KnowledgeBase, Document
from sqlalchemy import select, func

router = APIRouter()


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
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KnowledgeBaseRead.model_validate(kb)


@router.put("/knowledge/bases/{kb_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base(kb_id: int, body: KnowledgeBaseUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_WRITE))):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(kb, key, value)
    await db.commit()
    await db.refresh(kb)
    return KnowledgeBaseRead.model_validate(kb)


@router.delete("/knowledge/bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(kb_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_WRITE))):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await db.delete(kb)
    await db.commit()


@router.get("/knowledge/bases/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(kb_id: int, skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_READ))):
    total_result = await db.execute(select(func.count(Document.id)).where(Document.kb_id == kb_id))
    total = total_result.scalar()
    result = await db.execute(select(Document).where(Document.kb_id == kb_id).offset(skip).limit(limit))
    docs = result.scalars().all()
    return DocumentListResponse(total=total, documents=[DocumentRead.model_validate(d) for d in docs])


@router.post("/knowledge/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(body: KnowledgeQueryRequest, db: AsyncSession = Depends(get_db), _=Depends(require_permission(Permission.KNOWLEDGE_READ))):
    """
    Query knowledge base using embedding + rerank.
    For MVP, returns a stub response. Full implementation routes to
    the configured third-party embedding/rerank API.
    """
    # TODO: Integrate with user-configured embedding API (configured via /providers)
    # For now, return a stub indicating the query was received
    return KnowledgeQueryResponse(
        query=body.query,
        results=[],
        total=0,
        message="Embedding API not yet configured. Please configure a provider in AI Provider Config.",
    )
