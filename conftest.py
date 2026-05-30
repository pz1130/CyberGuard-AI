"""Root conftest — exclude integration smoke tests from normal pytest collection.

test_smoke_api.py uses ``asyncio.run()`` in ``setUpClass`` which creates a
separate event loop, poisoning the module-level SQLAlchemy async engine's
connection pool.  It is a standalone integration test that requires a running
server (SMOKE_BASE_URL) and should be run via:
    python -m unittest tests.test_smoke_api
"""
collect_ignore = ["tests/test_smoke_api.py"]
