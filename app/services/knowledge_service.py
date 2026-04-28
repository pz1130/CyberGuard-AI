"""Knowledge base service: chunking, embedding, and semantic search."""
import json
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeBase, Document
from app.services.llm_router import get_llm_router


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Vector math
# ---------------------------------------------------------------------------
def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class KnowledgeService:
    """Ingestion and retrieval against the knowledge base."""

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
        Chunk + embed text content and persist as a Document row.

        Returns the created Document (refreshed from DB).
        """
        kb = await db.get(KnowledgeBase, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        chunks = chunk_text(content)
        if not chunks:
            raise ValueError("Document is empty after chunking")

        embeddings = await self._embed(
            texts=chunks,
            embedding_model=kb.embedding_model,
            provider_id=provider_id,
        )

        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedding count mismatch: expected {len(chunks)}, got {len(embeddings)}"
            )

        chunks_payload = [
            {"text": chunk, "embedding": emb}
            for chunk, emb in zip(chunks, embeddings)
        ]

        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        doc = Document(
            kb_id=kb_id,
            filename=filename,
            content_chunks_json=json.dumps(chunks_payload),
            file_hash=file_hash,
            file_size=len(content.encode("utf-8")),
            mime_type=mime_type,
            metadata_json={"chunk_count": len(chunks)},
        )
        db.add(doc)
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
        Embed query and return top-k most similar chunks across the KB.

        Each result is a dict with keys: document_id, filename, text, score.
        """
        kb = await db.get(KnowledgeBase, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        result = await db.execute(
            select(Document).where(Document.kb_id == kb_id)
        )
        documents = result.scalars().all()
        if not documents:
            return []

        query_embeddings = await self._embed(
            texts=[query],
            embedding_model=kb.embedding_model,
            provider_id=provider_id,
        )
        if not query_embeddings:
            return []
        q_vec = query_embeddings[0]

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for doc in documents:
            try:
                payload = json.loads(doc.content_chunks_json or "[]")
            except json.JSONDecodeError:
                continue
            for idx, chunk in enumerate(payload):
                emb = chunk.get("embedding") or []
                score = cosine_similarity(q_vec, emb)
                if score < similarity_threshold:
                    continue
                scored.append((score, {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "chunk_index": idx,
                    "text": chunk.get("text", ""),
                    "score": round(score, 4),
                }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]


_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
