"""Episodic memory — record which approach succeeded for which task, and recall
similar past successes to prime future runs.

Storage is the dedicated `agent_episodes` table (task_embedding vector(1536)).
All operations are best-effort: an embed failure (e.g. the provider can't embed),
a DB error, or a missing table must never break an agent run — they log and
degrade to a no-op. See:
  docs/superpowers/specs/2026-06-02-episodic-memory-design.md
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

EPISODE_EMBED_MODEL = "text-embedding-3-small"
EPISODE_EMBED_DIM = 1536
OUTCOME_MAX_CHARS = 1000
# Cap growth: keep newest N episodes per agent after each record (failures + successes).
EPISODE_MAX_PER_AGENT = 200


def distill_approach(tool_call_log: List[Dict[str, Any]]) -> str:
    """Ordered, de-duplicated tool names joined by '→'. Pure / no side effects."""
    seen: List[str] = []
    for entry in tool_call_log or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if name and name not in seen:
            seen.append(name)
    return "→".join(seen)


class EpisodicMemoryService:
    def __init__(self, router=None):
        self._router = router

    @property
    def router(self):
        if self._router is None:
            from app.services.llm_router import get_llm_router
            self._router = get_llm_router()
        return self._router

    async def _embed(self, task: str, provider_id: Optional[int]) -> Optional[List[float]]:
        try:
            vecs = await self.router.embed(
                texts=[task], model=EPISODE_EMBED_MODEL, provider_id=provider_id)
        except Exception as e:                       # noqa: BLE001 - degrade gracefully
            logger.warning("episodic memory: embed failed: %s", e)
            return None
        if not vecs or len(vecs[0]) != EPISODE_EMBED_DIM:
            logger.warning("episodic memory: unexpected embedding shape; skipping")
            return None
        return vecs[0]

    async def recall(
        self, db, *, agent_id: int, task: str, top_k: int = 3,
        provider_id: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[float]]]:
        """Return (episodes, embedding) of the top-k most similar past successes
        for this agent. The embedding is returned so the caller can reuse it at
        record time (avoiding a second embed call)."""
        embedding = await self._embed(task, provider_id)
        if embedding is None:
            return [], None
        try:
            raw_sql = text(
                "SELECT task_text, approach, outcome, "
                "(1 - (task_embedding <=> (:q_vec)::vector(1536))) AS score "
                "FROM agent_episodes "
                "WHERE agent_id = :agent_id AND success = true "
                "ORDER BY task_embedding <=> (:q_vec)::vector(1536) "
                "LIMIT :top_k"
            )
            result = await db.execute(raw_sql, {
                "q_vec": json.dumps(embedding), "agent_id": agent_id, "top_k": top_k})
            rows = result.fetchall()
        except Exception as e:                       # noqa: BLE001
            logger.warning("episodic memory: recall query failed: %s", e)
            return [], embedding
        episodes = [
            {"task": r.task_text, "approach": r.approach, "outcome": r.outcome,
             "score": round(float(r.score), 4)}
            for r in rows
        ]
        return episodes, embedding

    async def record(
        self, db, *, agent_id: int, task: str, approach: str, outcome: str,
        success: bool = True, tool_count: int = 0,
        embedding: Optional[List[float]] = None, provider_id: Optional[int] = None,
        max_per_agent: int = EPISODE_MAX_PER_AGENT,
    ) -> None:
        """Insert one episode (success or failure). Best-effort; never raises.

        Recall still filters ``success = true``. Failures are retained for
        analysis and bounded by per-agent prune after insert.
        """
        if embedding is None:
            embedding = await self._embed(task, provider_id)
        if embedding is None:
            return
        outcome = (outcome or "")[:OUTCOME_MAX_CHARS]
        try:
            await db.execute(
                text(
                    "INSERT INTO agent_episodes "
                    "(agent_id, task_text, task_embedding, approach, outcome, "
                    " success, tool_count) "
                    "VALUES (:agent_id, :task_text, (:emb)::vector(1536), "
                    " :approach, :outcome, :success, :tool_count)"
                ),
                {"agent_id": agent_id, "task_text": task,
                 "emb": json.dumps(embedding), "approach": approach,
                 "outcome": outcome, "success": bool(success), "tool_count": tool_count},
            )
            if max_per_agent and max_per_agent > 0:
                await db.execute(
                    text(
                        "DELETE FROM agent_episodes "
                        "WHERE agent_id = :agent_id AND id NOT IN ("
                        "  SELECT id FROM agent_episodes "
                        "  WHERE agent_id = :agent_id "
                        "  ORDER BY created_at DESC NULLS LAST, id DESC "
                        "  LIMIT :keep"
                        ")"
                    ),
                    {"agent_id": agent_id, "keep": int(max_per_agent)},
                )
            await db.commit()
        except Exception as e:                       # noqa: BLE001
            logger.warning("episodic memory: record failed: %s", e)
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass


_service: Optional[EpisodicMemoryService] = None


def get_episodic_memory_service() -> EpisodicMemoryService:
    global _service
    if _service is None:
        _service = EpisodicMemoryService()
    return _service
