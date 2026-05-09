"""Knowledge base database models."""
from datetime import datetime
from sqlalchemy import Column, Float, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.core.database import Base


class KnowledgeBase(Base):
    """Knowledge base model."""

    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    rerank_model = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_encrypted = Column(Text, nullable=True)  # AES-256 encrypted
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<KnowledgeBase {self.name}>"


class Document(Base):
    """Document model within a knowledge base."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_chunks_json = Column(Text, nullable=True)  # Legacy JSON field — still used for migration compat
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document {self.filename} (kb={self.kb_id})>"


class DocumentChunk(Base):
    """Individual chunk with a stored vector embedding.

    Replaces the JSON blob in Document.content_chunks_json for large-scale
    semantic search using pgvector HNSW index.
    """

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    kb_id = Column(Integer, nullable=False)  # Denormalised for fast HNSW filtered queries
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    # 1536-dim float array matching text-embedding-3-small
    embedding = Column(ARRAY(Float()), nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    # HNSW index is managed via Alembic migration, not here (SQLAlchemy 2.x
    # does not yet have first-class HNSW index support in Table metadata).
    # Keep a plain index on document_id for fast lookups.
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
    )

    def __repr__(self):
        return f"<DocumentChunk {self.id} doc={self.document_id} idx={self.chunk_index}>"
