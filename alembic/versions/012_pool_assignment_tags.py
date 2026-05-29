"""unified pool assignment columns + pool tags

Revision ID: 012_pool_assignment_tags
Revises: 011_tool_executable
Create Date: 2026-05-29
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "012_pool_assignment_tags"
down_revision = "011_tool_executable"
branch_labels = None
depends_on = None


def _as_dict(meta):
    if meta is None:
        return None
    if isinstance(meta, dict):
        return dict(meta)
    if isinstance(meta, str):
        try:
            d = json.loads(meta)
            return d if isinstance(d, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def upgrade() -> None:
    op.add_column("agent_configs", sa.Column("associated_tools", sa.JSON(), nullable=True))
    op.add_column("agent_configs", sa.Column("associated_mcp_tools", sa.JSON(), nullable=True))
    op.add_column("skills", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("tools", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("mcp_tools", sa.Column("tags", sa.JSON(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, metadata_json FROM agent_configs")).fetchall()
    for rid, meta in rows:
        d = _as_dict(meta)
        if not d:
            continue
        tool_ids = d.pop("tool_ids", None)
        mcp_ids = d.pop("mcp_tool_ids", None)
        if tool_ids is None and mcp_ids is None:
            continue
        conn.execute(
            text("UPDATE agent_configs SET "
                 "associated_tools = CAST(:t AS JSON), "
                 "associated_mcp_tools = CAST(:m AS JSON), "
                 "metadata_json = CAST(:meta AS JSON) WHERE id = :id"),
            {"t": json.dumps(tool_ids) if tool_ids is not None else None,
             "m": json.dumps(mcp_ids) if mcp_ids is not None else None,
             "meta": json.dumps(d), "id": rid},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT id, metadata_json, associated_tools, associated_mcp_tools "
             "FROM agent_configs")).fetchall()
    for rid, meta, tool_ids, mcp_ids in rows:
        if tool_ids is None and mcp_ids is None:
            continue
        d = _as_dict(meta) or {}
        if tool_ids is not None:
            d["tool_ids"] = tool_ids if not isinstance(tool_ids, str) else json.loads(tool_ids)
        if mcp_ids is not None:
            d["mcp_tool_ids"] = mcp_ids if not isinstance(mcp_ids, str) else json.loads(mcp_ids)
        conn.execute(
            text("UPDATE agent_configs SET metadata_json = CAST(:meta AS JSON) WHERE id = :id"),
            {"meta": json.dumps(d), "id": rid},
        )
    op.drop_column("mcp_tools", "tags")
    op.drop_column("tools", "tags")
    op.drop_column("skills", "tags")
    op.drop_column("agent_configs", "associated_mcp_tools")
    op.drop_column("agent_configs", "associated_tools")
