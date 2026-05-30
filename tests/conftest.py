"""Test configuration — session-scoped async engine disposal."""
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def dispose_engine():
    """Dispose the SQLAlchemy async engine after the entire test session.

    The engine is a module-level singleton in app.core.database.  With a
    session-scoped event loop (asyncio_default_test_loop_scope = "session"
    in pyproject.toml), the engine is bound to that single loop for the whole
    run.  This fixture ensures the connection pool is closed cleanly at the end
    so asyncpg doesn't log 'connection was closed in the middle of operation'.
    """
    yield
    from app.core.database import engine
    await engine.dispose()
