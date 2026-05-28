"""agent kind and internal-agent columns

Revision ID: 010_agent_kind_and_internal
Revises: 009_req_typical_evidence
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa


revision = "010_agent_kind_and_internal"
down_revision = "009_req_typical_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: conversations table has no prior migration in chain 001–009.
    # On existing DBs (created manually or via pre-Alembic process) this is
    # a no-op; on fresh installs it creates the table so the ADD COLUMN calls
    # below don't fail with "relation conversations does not exist".
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            title VARCHAR(200) DEFAULT '新对话',
            messages_json TEXT DEFAULT '[]',
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            system_prompt_override TEXT,
            intent_parser_prompt_override TEXT,
            summarizer_prompt_override TEXT,
            model_override VARCHAR(100),
            temperature_override REAL,
            knowledge_base_id INTEGER REFERENCES knowledge_bases(id)
        )
    """)

    # agent_configs
    op.add_column("agent_configs", sa.Column("kind", sa.String(20),
                                              nullable=False, server_default="external"))
    op.add_column("agent_configs", sa.Column("llm_provider_id", sa.Integer,
                                              sa.ForeignKey("providers.id", ondelete="SET NULL"),
                                              nullable=True))
    op.add_column("agent_configs", sa.Column("llm_model", sa.String(100), nullable=True))
    op.add_column("agent_configs", sa.Column("tool_loop_max_steps", sa.Integer,
                                              nullable=False, server_default="8"))
    op.add_column("agent_configs", sa.Column("memory_window", sa.Integer,
                                              nullable=False, server_default="20"))
    op.add_column("agent_configs", sa.Column("knowledge_base_id", sa.Integer,
                                              sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
                                              nullable=True))
    op.create_index("ix_agent_configs_kind", "agent_configs", ["kind"])
    # Backfill — every existing row was external by definition
    op.execute("UPDATE agent_configs SET kind='external'")

    # conversations — slice memory per internal agent + parent link
    op.add_column("conversations", sa.Column("agent_id", sa.Integer,
                                              sa.ForeignKey("agent_configs.id", ondelete="CASCADE"),
                                              nullable=True))
    op.add_column("conversations", sa.Column("parent_conversation_id", sa.Integer,
                                              sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                                              nullable=True))
    op.create_index("ix_conv_agent", "conversations", ["agent_id", "parent_conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_conv_agent", table_name="conversations")
    op.drop_column("conversations", "parent_conversation_id")
    op.drop_column("conversations", "agent_id")
    op.drop_index("ix_agent_configs_kind", table_name="agent_configs")
    op.drop_column("agent_configs", "knowledge_base_id")
    op.drop_column("agent_configs", "memory_window")
    op.drop_column("agent_configs", "tool_loop_max_steps")
    op.drop_column("agent_configs", "llm_model")
    op.drop_column("agent_configs", "llm_provider_id")
    op.drop_column("agent_configs", "kind")
