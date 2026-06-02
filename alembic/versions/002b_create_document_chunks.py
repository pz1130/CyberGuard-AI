"""Create document_chunks table — bridge migration for the missing initial DDL.

Revision ID: 002b_create_document_chunks
Revises: 002_openclaw_gateway
Create Date: 2026-06-02 00:00:00.000000

`alembic/versions/001_initial.py` creates `knowledge_bases` and `documents` but
never creates `document_chunks`. Migration `003_pgvector_knowledge` then
`ALTER TABLE document_chunks …`, which fails on a fresh DB with
`UndefinedTableError: relation "document_chunks" does not exist`. This is a
long-standing gap in the migration chain, surfaced while testing PR #9
(episodic memory) end-to-end on a real Postgres+pgvector database.

This bridge creates the table in the **legacy ARRAY-typed** shape that
`001_initial.py` would have used (and that `003_pgvector_knowledge` then
`DROP … ADD …`s into the pgvector `vector(1536)` column). It must come
**before 003** in the chain so that migration sees the table it expects.

The shape mirrors `app/models/knowledge.DocumentChunk` minus the post-004
columns (`embedding_large`, the `ck_document_chunks_one_embedding` CHECK) —
those are added later by `004_multi_dim_embeddings` on top of the pgvector
column. Keeping them out of this bridge preserves 004's role as the
multi-dim migration and avoids re-running or re-defining constraints here.

Existing rows: none. `001_initial` never created the table, so there is no
historical data to preserve. The `embedding` column starts as the legacy
`double precision[] NOT NULL` so that the explicit NOT NULL is honoured on
fresh DBs (where the table is created for the first time) without 003's
downstream `ALTER … DROP NOT NULL` losing data on tables that already had
data, since there is none. 003's upgrade path of `DROP COLUMN IF EXISTS` +
`ADD COLUMN … NOT NULL` is the documented non-data-preserving transition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "002b_create_document_chunks"
down_revision: Union[str, None] = "002_openclaw_gateway"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float, dimensions=1), nullable=False),
        # Note: postgresql.ARRAY(..., dimensions=1) renders as `double precision[]`
        # which is the legacy shape 001 would have produced and 003 then DROPs.
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_chunks_id"), "document_chunks", ["id"], unique=False)
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
