"""Pydantic schemas for knowledge base and document management."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class KnowledgeBaseBase(BaseModel):
    """Base knowledge base schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    rerank_model: Optional[str] = None
    is_active: bool = True


class KnowledgeBaseCreate(KnowledgeBaseBase):
    """Knowledge base creation schema."""
    metadata_json: Optional[Dict[str, Any]] = None


class KnowledgeBaseUpdate(BaseModel):
    """Knowledge base update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    rerank_model: Optional[str] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[Dict[str, Any]] = None


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response schema."""
    id: int
    name: str
    description: Optional[str]
    embedding_model: Optional[str]
    rerank_model: Optional[str]
    is_active: bool
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    """Paginated knowledge base list response."""
    total: int
    knowledge_bases: list[KnowledgeBaseResponse]


class DocumentBase(BaseModel):
    """Base document schema."""
    kb_id: int
    filename: str = Field(..., min_length=1, max_length=255)


class DocumentCreate(DocumentBase):
    """Document creation schema."""
    content_chunks_json: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DocumentUpdate(BaseModel):
    """Document update schema."""
    content_chunks_json: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DocumentResponse(BaseModel):
    """Document response schema."""
    id: int
    kb_id: int
    filename: str
    content_chunks_json: Optional[str]
    file_hash: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentUploadResponse(BaseModel):
    """Document upload response schema."""
    document_id: int
    filename: str
    file_hash: str
    status: str
    chunks_count: Optional[int] = None


class KnowledgeQueryRequest(BaseModel):
    """Knowledge base query request schema."""
    kb_id: int
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class KnowledgeQueryResponse(BaseModel):
    """Knowledge base query response schema."""
    results: List[Dict[str, Any]]
    query: str
    kb_id: int

# Aliases
KnowledgeBaseRead = KnowledgeBaseResponse
DocumentRead = DocumentResponse
DocumentListResponse = list[DocumentResponse]
