"""LangGraph checkpointer factory.

The master graph needs a durable checkpointer so ``interrupt()`` can suspend an
approval without holding a worker for an hour, and so a different process can
resume after an admin decides.

* Production / normal runtime: ``AsyncPostgresSaver`` over a short-lived
  psycopg pool (works across Celery workers and event-loop restarts).
* Tests / explicit override: ``MemorySaver`` (in-process, no DB tables).

Callers that create a new event loop per task (Celery) should use the context
manager form so the pool is opened and closed on that loop.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_ENV_BACKEND = "GRAPH_CHECKPOINT_BACKEND"  # "memory" | "postgres" | unset


def _postgres_conninfo() -> str:
    """Translate the app's SQLAlchemy URL into a psycopg conninfo string."""
    url = settings.DATABASE_URL
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def use_memory_checkpointer() -> bool:
    backend = (os.environ.get(_ENV_BACKEND) or "").strip().lower()
    if backend == "memory":
        return True
    if backend == "postgres":
        return False
    # Prefer memory under pytest so unit tests stay offline and fast.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return False


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[Any]:
    """Yield a checkpointer bound to the current event loop.

    Always open a fresh Postgres pool (or a fresh MemorySaver) so Celery's
    "new loop per task" pattern cannot leave us with a closed-loop pool.
    """
    if use_memory_checkpointer():
        from langgraph.checkpoint.memory import MemorySaver
        yield MemorySaver()
        return

    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    pool: Optional[AsyncConnectionPool] = None
    try:
        pool = AsyncConnectionPool(
            conninfo=_postgres_conninfo(),
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
            min_size=1,
            max_size=4,
        )
        await pool.open()
        saver = AsyncPostgresSaver(pool)
        # Idempotent: creates checkpoint tables on first use.
        await saver.setup()
        yield saver
    finally:
        if pool is not None:
            try:
                await pool.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("graph checkpointer pool close failed: %s", e)
