"""Knowledge base database models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index, CheckConstraint
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector, HALFVEC
from app.core.database import Base

# Supported embedding dimensions and the column each maps to.
# Add new dims by creating a new column + HNSW index via Alembic, then
# extending this map. Service code routes by KB.embedding_dim.
EMBEDDING_DIM_SMALL = 1536   # text-embedding-3-small, text-embedding-ada-002
EMBEDDING_DIM_LARGE = 3072   # text-embedding-3-large
SUPPORTED_EMBEDDING_DIMS = (EMBEDDING_DIM_SMALL, EMBEDDING_DIM_LARGE)
DEFAULT_EMBEDDING_DIM = EMBEDDING_DIM_SMALL

# Map dim → SQLAlchemy column name on DocumentChunk. KnowledgeService uses
# this to decide which column to write/query.
EMBEDDING_COLUMN_BY_DIM = {
    EMBEDDING_DIM_SMALL: "embedding",
    EMBEDDING_DIM_LARGE: "embedding_large",
}


class KnowledgeBase(Base):
    """Knowledge base model."""

    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    # Dimension of vectors produced by `embedding_model`. Locked at KB creation —
    # cannot change without re-embedding all docs. CHECK enforced in DB.
    embedding_dim = Column(Integer, nullable=False, default=DEFAULT_EMBEDDING_DIM)
    rerank_model = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_encrypted = Column(Text, nullable=True)  # AES-256 encrypted
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"embedding_dim IN ({EMBEDDING_DIM_SMALL}, {EMBEDDING_DIM_LARGE})",
            name="ck_knowledge_bases_embedding_dim",
        ),
    )

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
    # Exactly one embedding column is populated per chunk, matching the KB's
    # `embedding_dim`. CHECK constraint enforces XOR. HNSW indexes on both,
    # built in Alembic 003 (small) and 004 (large).
    embedding = Column(Vector(EMBEDDING_DIM_SMALL), nullable=True)         # vector(1536)
    # HNSW with `vector` caps at 2000 dims; 3072 must use halfvec (16-bit, HNSW up to 4000).
    # Precision loss is negligible for cosine similarity.
    embedding_large = Column(HALFVEC(EMBEDDING_DIM_LARGE), nullable=True)  # halfvec(3072)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        CheckConstraint(
            "(embedding IS NOT NULL)::int + (embedding_large IS NOT NULL)::int = 1",
            name="ck_document_chunks_one_embedding",
        ),
    )

    def __repr__(self):
        return f"<DocumentChunk {self.id} doc={self.document_id} idx={self.chunk_index}>"
