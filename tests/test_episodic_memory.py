"""Tests for episodic memory (app/services/episodic_memory.py).

DB and embeddings are mocked, so these run without Postgres or a provider.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.episodic_memory import EpisodicMemoryService, distill_approach


def test_distill_approach_orders_and_dedups_tool_names():
    log = [
        {"name": "web_search", "arguments": "{}"},
        {"name": "vuln_search", "arguments": "{}"},
        {"name": "web_search", "arguments": "{}"},   # repeat collapses
        {"name": "kb_search", "arguments": "{}"},
    ]
    assert distill_approach(log) == "web_search→vuln_search→kb_search"


def test_distill_approach_empty():
    assert distill_approach([]) == ""


def _vec():
    return [0.0] * 1536


def _fake_router(vec=None):
    r = MagicMock()
    r.embed = AsyncMock(return_value=[vec if vec is not None else _vec()])
    return r


@pytest.mark.asyncio
async def test_recall_runs_agent_scoped_ann_and_returns_embedding():
    row = MagicMock(task_text="scan host", approach="web_search→vuln_search",
                    outcome="found CVE", score=0.91)
    result = MagicMock()
    result.fetchall.return_value = [row]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    svc = EpisodicMemoryService(router=_fake_router())
    episodes, emb = await svc.recall(db, agent_id=7, task="scan host", top_k=3)

    assert emb is not None and len(emb) == 1536
    assert episodes == [{"task": "scan host", "approach": "web_search→vuln_search",
                         "outcome": "found CVE", "score": 0.91}]
    sql, params = db.execute.call_args.args
    assert "success = true" in str(sql).lower() or "success = true" in str(sql)
    assert params["agent_id"] == 7 and params["top_k"] == 3


@pytest.mark.asyncio
async def test_record_inserts_and_reuses_supplied_embedding():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    router = _fake_router()
    svc = EpisodicMemoryService(router=router)

    await svc.record(db, agent_id=7, task="scan host",
                     approach="web_search→vuln_search", outcome="x" * 5000,
                     tool_count=2, embedding=_vec())

    router.embed.assert_not_called()                 # reused supplied embedding
    # Two statements now: the insert, then the per-agent prune.
    assert db.execute.await_count == 2
    insert_sql, params = db.execute.await_args_list[0].args
    assert "INSERT INTO agent_episodes" in str(insert_sql)
    assert params["agent_id"] == 7 and params["tool_count"] == 2
    assert len(params["outcome"]) == 1000            # truncated to OUTCOME_MAX_CHARS
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_prunes_oldest_episodes_beyond_the_cap():
    """Recall always takes the top-k nearest neighbours, so an uncapped table
    lets one early bad episode stay attached to a task shape forever."""
    from app.services.episodic_memory import EPISODE_MAX_PER_AGENT

    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    svc = EpisodicMemoryService(router=_fake_router())

    await svc.record(db, agent_id=7, task="t", approach="a", outcome="o",
                     embedding=_vec())

    prune_sql, params = db.execute.await_args_list[1].args
    assert "DELETE FROM agent_episodes" in str(prune_sql)
    assert params == {"agent_id": 7, "keep": EPISODE_MAX_PER_AGENT}


@pytest.mark.asyncio
async def test_record_persists_the_supplied_success_flag():
    """success must reflect how the run actually ended; recall filters on it."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    svc = EpisodicMemoryService(router=_fake_router())

    await svc.record(db, agent_id=7, task="t", approach="a", outcome="o",
                     success=False, embedding=_vec())

    _, params = db.execute.await_args_list[0].args
    assert params["success"] is False


@pytest.mark.asyncio
async def test_recall_degrades_when_embed_fails():
    router = MagicMock()
    router.embed = AsyncMock(side_effect=RuntimeError("no embeddings"))
    db = MagicMock(); db.execute = AsyncMock()
    svc = EpisodicMemoryService(router=router)

    episodes, emb = await svc.recall(db, agent_id=1, task="t")
    assert episodes == [] and emb is None
    db.execute.assert_not_called()                   # never queried
