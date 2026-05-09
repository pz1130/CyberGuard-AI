"""Knowledge base service: chunking, embedding, and semantic search."""
import json
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeBase, Document, DocumentChunk
from app.services.llm_router import get_llm_router


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping chunks. Operates on characters for simplicity.

    Args:
        text: input text
        chunk_size: max characters per chunk
        overlap: characters of overlap between consecutive chunks

    Returns:
        list of chunk strings (non-empty)
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------
class KnowledgeService:
    """Ingestion and retrieval against the knowledge base.

    Uses pgvector HNSW index on document_chunks.embedding for ANN search.
    Cosine similarity = 1 - vector_cosine_distance.
    """

    def __init__(self):
        self.router = get_llm_router()

    async def _embed(
        self,
        texts: List[str],
        embedding_model: Optional[str],
        provider_id: Optional[int] = None,
    ) -> List[List[float]]:
        """Embed a list of texts via the configured AI Provider."""
        return await self.router.embed(
            texts=texts,
            model=embedding_model,
            provider_id=provider_id,
        )

    async def ingest_document(
        self,
        db: AsyncSession,
        kb_id: int,
        filename: str,
        content: str,
        mime_type: Optional[str] = None,
        provider_id: Optional[int] = None,
    ) -> Document:
        """
        Chunk + embed text content and persist as Document + DocumentChunk rows.

        Stores each chunk with its embedding vector in the document_chunks table
        (pgvector + HNSW index) instead of a JSON blob.

        Returns the created Document (refreshed from DB).
        """
        kb = await db.get(KnowledgeBase, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        chunks = chunk_text(content)
        if not chunks:
            raise ValueError("Document is empty after chunking")

        # Batch embed all chunks in one API call
        embeddings = await self._embed(
            texts=chunks,
            embedding_model=kb.embedding_model,
            provider_id=provider_id,
        )

        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedding count mismatch: expected {len(chunks)}, got {len(embeddings)}"
            )

        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Create the Document record first
        doc = Document(
            kb_id=kb_id,
            filename=filename,
            content_chunks_json=None,  # Deprecated — vectors now in document_chunks
            file_hash=file_hash,
            file_size=len(content.encode("utf-8")),
            mime_type=mime_type,
            metadata_json={"chunk_count": len(chunks)},
        )
        db.add(doc)
        await db.flush()  # Get doc.id without committing

        # Create one DocumentChunk per chunk (vectors stored in pgvector ARRAY column)
        chunk_records = [
            DocumentChunk(
                document_id=doc.id,
                kb_id=kb_id,
                chunk_index=i,
                content=chunk,
                embedding=emb,  # List[float] — SQLAlchemy ARRAY column handles conversion
                metadata_json={"filename": filename},
            )
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
        ]

        db.add_all(chunk_records)
        await db.commit()
        await db.refresh(doc)
        return doc

    async def query(
        self,
        db: AsyncSession,
        kb_id: int,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
        provider_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Embed query and return top-k most similar chunks using pgvector HNSW ANN.

        Cosine distance is used (vector_cosine_ops in HNSW); similarity =
        1 - cosine_distance.  Results below similarity_threshold are filtered.

        Returns list of dicts with keys: document_id, filename, chunk_index,
        content, score.
        """
        kb = await db.get(KnowledgeBase, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        query_embeddings = await self._embed(
            texts=[query],
            embedding_model=kb.embedding_model,
            provider_id=provider_id,
        )
        if not query_embeddings:
            return []

        q_vec = query_embeddings[0]

        # Use raw SQL for the ANN query — pgvector's vector_cosine_distance
        # requires an ARRAY literal on the Python side; JSON cast is the most
        # portable approach across asyncpg / psycopg2.
        import json as _json
        q_vec_json = _json.dumps(q_vec)

        raw_sql = text("""
            SELECT
                dc.document_id,
                dc.chunk_index,
                dc.content,
                (1 - (dc.embedding <=> (:q_vec)::vector)) AS score
            FROM document_chunks dc
            WHERE dc.kb_id = :kb_id
            ORDER BY dc.embedding <=> (:q_vec)::vector
            LIMIT :top_k
        """)

        result = await db.execute(
            raw_sql,
            {"q_vec": q_vec_json, "kb_id": kb_id, "top_k": top_k},
        )
        rows = result.fetchall()

        if not rows:
            return []

        # Fetch filenames in a single query
        doc_ids = list({r.document_id for r in rows})
        docs_result = await db.execute(
            select(Document.id, Document.filename).where(Document.id.in_(doc_ids))
        )
        doc_names = {row[0]: row[1] for row in docs_result.all()}

        results = []
        for row in rows:
            score: float = row.score  # type: ignore[assignment]
            if score < similarity_threshold:
                continue
            results.append({
                "document_id": row.document_id,
                "filename": doc_names.get(row.document_id, "unknown"),
                "chunk_index": row.chunk_index,
                "content": row.content,
                "score": round(score, 4),
            })

        return results

    async def delete_document_chunks(self, db: AsyncSession, document_id: int) -> int:
        """Delete all chunks for a document. Called on document deletion."""
        result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        chunks = result.scalars().all()
        count = len(chunks)
        for chunk in chunks:
            await db.delete(chunk)
        await db.commit()
        return count


_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
