"""Initial schema migration

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('permissions_json', sa.Text(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    # Agent configs table
    op.create_table(
        'agent_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_name', sa.String(length=100), nullable=False),
        sa.Column('backend_type', sa.String(length=50), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=True),
        sa.Column('endpoint_url', sa.String(length=500), nullable=True),
        sa.Column('env_vars_encrypted', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('permission_level', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('associated_skills', sa.JSON(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_configs_id'), 'agent_configs', ['id'], unique=False)
    op.create_index(op.f('ix_agent_configs_agent_name'), 'agent_configs', ['agent_name'], unique=True)

    # Agent executions table
    op.create_table(
        'agent_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.String(length=36), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('input_data', sa.JSON(), nullable=True),
        sa.Column('output_data', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_executions_id'), 'agent_executions', ['id'], unique=False)
    op.create_index(op.f('ix_agent_executions_execution_id'), 'agent_executions', ['execution_id'], unique=True)

    # Skills table
    op.create_table(
        'skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('md_content', sa.Text(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('permission_level', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_skills_id'), 'skills', ['id'], unique=False)
    op.create_index(op.f('ix_skills_name'), 'skills', ['name'], unique=True)

    # Tools table
    op.create_table(
        'tools',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('md_content', sa.Text(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('permission_level', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tools_id'), 'tools', ['id'], unique=False)
    op.create_index(op.f('ix_tools_name'), 'tools', ['name'], unique=True)

    # Knowledge bases table
    op.create_table(
        'knowledge_bases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('rerank_model', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata_encrypted', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_knowledge_bases_id'), 'knowledge_bases', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_bases_name'), 'knowledge_bases', ['name'], unique=True)

    # Documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kb_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_chunks_json', sa.Text(), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['kb_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=False)

    # Audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('agent_id', sa.String(length=100), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.Column('output_hash', sa.String(length=64), nullable=False),
        sa.Column('request_id', sa.String(length=36), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)

    # Providers table
    op.create_table(
        'providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('provider_type', sa.String(length=50), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('base_url', sa.String(length=500), nullable=True),
        sa.Column('api_version', sa.String(length=50), nullable=True),
        sa.Column('models', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_providers_id'), 'providers', ['id'], unique=False)
    op.create_index(op.f('ix_providers_name'), 'providers', ['name'], unique=True)

    # MCP servers table
    op.create_table(
        'mcp_servers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('transport_type', sa.String(length=20), nullable=False, server_default='stdio'),
        sa.Column('command', sa.String(length=500), nullable=True),
        sa.Column('args', sa.JSON(), nullable=True),
        sa.Column('env_vars_encrypted', sa.Text(), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('auth_token_encrypted', sa.Text(), nullable=True),
        sa.Column('headers_json', sa.JSON(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True, server_default='30'),
        sa.Column('process_id', sa.Integer(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_mcp_servers_id'), 'mcp_servers', ['id'], unique=False)
    op.create_index(op.f('ix_mcp_servers_name'), 'mcp_servers', ['name'], unique=True)

    # MCP tools table
    op.create_table(
        'mcp_tools',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('server_id', sa.Integer(), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('input_schema_json', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('use_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('required_permission', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['server_id'], ['mcp_servers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_mcp_tools_id'), 'mcp_tools', ['id'], unique=False)
    op.create_index(op.f('ix_mcp_tools_tool_name'), 'mcp_tools', ['tool_name'], unique=False)
    op.create_index(op.f('ix_mcp_tools_required_permission'), 'mcp_tools', ['required_permission'], unique=False)

    # Env vars table
    op.create_table(
        'env_vars',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('value_encrypted', sa.Text(), nullable=False),
        sa.Column('value_type', sa.String(length=20), nullable=False, server_default='text'),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_env_vars_id'), 'env_vars', ['id'], unique=False)
    op.create_index(op.f('ix_env_vars_key'), 'env_vars', ['key'], unique=True)

    # Token usage logs table
    op.create_table(
        'token_usage_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('provider_name', sa.String(length=100), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('prompt_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('call_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('date_str', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_token_usage_logs_id'), 'token_usage_logs', ['id'], unique=False)
    op.create_index(op.f('ix_token_usage_logs_model_name'), 'token_usage_logs', ['model_name'], unique=False)
    op.create_index(op.f('ix_token_usage_logs_date_str'), 'token_usage_logs', ['date_str'], unique=False)


def downgrade() -> None:
    op.drop_table('token_usage_logs')
    op.drop_table('env_vars')
    op.drop_table('mcp_tools')
    op.drop_table('mcp_servers')
    op.drop_table('providers')
    op.drop_table('audit_logs')
    op.drop_table('documents')
    op.drop_table('knowledge_bases')
    op.drop_table('tools')
    op.drop_table('skills')
    op.drop_table('agent_executions')
    op.drop_table('agent_configs')
    op.drop_table('roles')
    op.drop_table('users')