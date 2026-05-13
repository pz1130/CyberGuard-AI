"""Per-KB embedding dimension; add 3072-dim column + HNSW + CHECK.

Revision ID: 004_multi_dim_embeddings
Revises: 003_pgvector_knowledge
Create Date: 2026-05-12 12:00:00.000000

Adds:
  - knowledge_bases.embedding_dim (NOT NULL, default 1536, CHECK in (1536, 3072))
  - document_chunks.embedding becomes NULLABLE
  - document_chunks.embedding_large vector(3072) NULLABLE
  - CHECK: exactly one of (embedding, embedding_large) is non-null per row
  - HNSW index on embedding_large (partial: WHERE NOT NULL)

Why partial indexes: each chunk only populates one column, so the other half of
each row's index entry would be a NULL bloat. `WHERE col IS NOT NULL` keeps the
HNSW build cheap and queries against the populated column index-bound.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "004_multi_dim_embeddings"
down_revision: Union[str, None] = "003_pgvector_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. knowledge_bases.embedding_dim
    op.execute(
        "ALTER TABLE knowledge_bases "
        "ADD COLUMN embedding_dim INTEGER NOT NULL DEFAULT 1536"
    )
    op.execute(
        "ALTER TABLE knowledge_bases "
        "ADD CONSTRAINT ck_knowledge_bases_embedding_dim "
        "CHECK (embedding_dim IN (1536, 3072))"
    )

    # 2. Make existing embedding column nullable (was NOT NULL in migration 003).
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding DROP NOT NULL")

    # 3. Add embedding_large as halfvec(3072) — full-precision `vector` HNSW
    #    caps at 2000 dims (pgvector index entry size limit), but `halfvec`
    #    (16-bit float) supports HNSW up to 4000 dims. Precision loss is
    #    negligible for cosine similarity on embeddings.
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding_large halfvec(3072)")

    # 4. XOR constraint — exactly one non-null per row.
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD CONSTRAINT ck_document_chunks_one_embedding "
        "CHECK ((embedding IS NOT NULL)::int + (embedding_large IS NOT NULL)::int = 1)"
    )

    # 5. Partial HNSW index on embedding_large with halfvec_cosine_ops.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_large_hnsw "
        "ON document_chunks USING hnsw (embedding_large halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64) "
        "WHERE embedding_large IS NOT NULL"
    )

    # 6. Recreate the small-dim HNSW as partial too (so NULL rows don't bloat it).
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_large_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute(
        "ALTER TABLE document_chunks DROP CONSTRAINT IF EXISTS ck_document_chunks_one_embedding"
    )
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_large")
    # Restore NOT NULL on the small column. WARNING: fails if any rows have NULL embedding
    # (i.e., were ingested under the new 3072 path) — drop them or downgrade after re-embed.
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding SET NOT NULL")
    # Restore the non-partial HNSW (matches migration 003 final state).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.execute(
        "ALTER TABLE knowledge_bases DROP CONSTRAINT IF EXISTS ck_knowledge_bases_embedding_dim"
    )
    op.execute("ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS embedding_dim")
