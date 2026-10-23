"""Test configuration — test-database guard and session-scoped engine disposal."""
import pytest
import pytest_asyncio


def pytest_collection_modifyitems(config, items):
    """Refuse to run against a database that is not a test database.

    The suite creates and hard-deletes users, conversations and audit rows.
    Bare ``pytest`` takes DATABASE_URL from .env, which names the development
    database, and hard-deleting test accounts in a real database is what
    stripped the actor from 51 signed audit rows in the preview
    (docs/audit-chain-investigation-20260918.md). ``make test`` points the
    suite at a disposable ``cyberguard_test``.

    Smoke tests require explicit mutation opt-in and a testing environment.
    """
    from sqlalchemy.engine import make_url

    from app.config import settings

    database = make_url(settings.DATABASE_URL).database or ""
    if database.endswith("_test"):
        return
    if items and all(item.path.name == "test_smoke_api.py" for item in items):
        from tests.test_smoke_api import _require_disposable_smoke_environment
        _require_disposable_smoke_environment()
        return
    pytest.exit(
        f"Refusing to run tests against database {database!r}: they create and "
        "delete users and audit records. Run `make test`, or point DATABASE_URL "
        "at a *_test database.",
        returncode=pytest.ExitCode.USAGE_ERROR,
    )


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
