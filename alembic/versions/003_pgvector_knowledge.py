"""Enable pgvector and convert document_chunks.embedding to vector(1536) + HNSW.

Revision ID: 003_pgvector_knowledge
Revises: 002_openclaw_gateway
Create Date: 2026-05-12 00:00:00.000000

Background:
    The KnowledgeBase service stores chunk embeddings and performs cosine
    similarity ANN search via `<=>`. Both require the `vector` type from
    the pgvector extension. The initial schema mistakenly used Postgres
    native `double precision[]`, which leaves the ANN path broken.

This migration:
  1. Installs the `vector` extension (no-op if present).
  2. Drops the empty/legacy `embedding` column (assumed empty — KB feature
     was non-functional, so no data to preserve. If you have data, run a
     re-embed pass before applying this).
  3. Recreates `embedding` as `vector(1536)`.
  4. Creates an HNSW index with vector_cosine_ops so the existing
     `ORDER BY embedding <=> :q_vec` query is index-backed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_pgvector_knowledge"
down_revision: Union[str, None] = "002_openclaw_gateway"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EMBEDDING_DIM = 1536


def upgrade() -> None:
    # 1. Ensure pgvector extension is loaded.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Drop legacy column. Safe because the previous ARRAY-typed embeddings
    #    are unusable for the `<=>` operator and cannot be cast cleanly to
    #    vector via ALTER COLUMN USING (asyncpg quirks with ARRAY→vector).
    #    If you somehow accumulated rows, re-ingest the documents after
    #    upgrade.
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")

    # 3. Add the vector column back. NOT NULL is enforced from the model,
    #    but new rows from the service always supply a vector so we keep
    #    NOT NULL for data integrity.
    op.execute(
        f"ALTER TABLE document_chunks ADD COLUMN embedding vector({EMBEDDING_DIM}) NOT NULL"
    )

    # 4. HNSW index for cosine ANN. `vector_cosine_ops` matches the `<=>`
    #    operator used in KnowledgeService.query. m=16, ef_construction=64
    #    are pgvector defaults — fine for up to ~1M vectors. Tune later
    #    if recall/latency become an issue.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    # Restore the legacy ARRAY column so 002-era code still works.
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN embedding double precision[] NOT NULL"
    )
    # Intentionally do NOT drop the extension — other tables/queries may use it.
