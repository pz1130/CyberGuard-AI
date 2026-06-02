"""Create agent_episodes table (episodic memory) with a vector(1536) + HNSW index.

Revision ID: 017_agent_episodes
Revises: 016_ocr
Create Date: 2026-06-02 00:00:00.000000

Episodic memory records which approach succeeded for which task and recalls
similar past successes to prime future runs. The `task_embedding` column +
HNSW cosine index back the ANN recall query in
`app/services/episodic_memory.py`, mirroring `003_pgvector_knowledge`.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "017_agent_episodes"
down_revision: Union[str, None] = "016_ocr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    # pgvector is already installed (003), but keep idempotent for safety.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS agent_episodes (
            id              SERIAL PRIMARY KEY,
            agent_id        INTEGER NOT NULL,
            task_text       TEXT NOT NULL,
            task_embedding  vector({EMBEDDING_DIM}) NOT NULL,
            approach        TEXT,
            outcome         TEXT,
            success         BOOLEAN NOT NULL DEFAULT TRUE,
            tool_count      INTEGER NOT NULL DEFAULT 0,
            metadata_json   JSON,
            created_at      TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )

    # Composite btree for the agent-scoped, success-filtered recall.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_episodes_agent_success "
        "ON agent_episodes (agent_id, success)"
    )

    # HNSW cosine index backing `task_embedding <=> :q_vec` ANN ordering.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_episodes_embedding_hnsw "
        "ON agent_episodes USING hnsw (task_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_episodes_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_agent_episodes_agent_success")
    op.execute("DROP TABLE IF EXISTS agent_episodes")
    # Intentionally do NOT drop the vector extension — other tables use it.
