"""The indexes search depends on, asserted against the real database.

Round 1's spec planned a tsvector column. Measured, PostgreSQL tokenises a
whole Chinese sentence as one lexeme — `to_tsvector('english', '扫描主机的开放
端口')` is a single term, and searching 端口 does not match it. These tests pin
the pg_trgm arrangement that replaced it, including the property that made the
partial index worth having.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def _scalar(sql: str):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql))).scalar()


@pytest.mark.asyncio
async def test_pg_trgm_is_installed():
    assert await _scalar("SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'") == 1


@pytest.mark.asyncio
async def test_the_content_index_is_a_trigram_gin_index():
    definition = await _scalar(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname='ix_conv_messages_content_trgm'")
    assert definition is not None, "the content index is missing"
    assert "USING gin" in definition
    assert "gin_trgm_ops" in definition


@pytest.mark.asyncio
async def test_the_owner_index_excludes_tombstones_and_agent_slices():
    """The predicate is the point: a deleted or agent-internal conversation is
    absent from the index rather than filtered out by each query that
    remembers to."""
    definition = await _scalar(
        "SELECT indexdef FROM pg_indexes WHERE indexname='ix_conv_user_live'")
    assert definition is not None, "the owner index is missing"
    assert "WHERE" in definition
    assert "deleted_at IS NULL" in definition
    assert "agent_id IS NULL" in definition


@pytest.mark.asyncio
async def test_full_text_search_would_not_have_worked_for_chinese():
    """Kept as a regression guard on the decision, not on our code: if someone
    later proposes tsvector again, this is the measurement that says no."""
    matched = await _scalar(
        "SELECT to_tsvector('simple', '扫描主机的开放端口') "
        "@@ plainto_tsquery('simple', '端口')")
    assert matched is False, (
        "PostgreSQL now segments Chinese — revisit the search design, because "
        "full-text search would be better than trigram matching")
