"""In-place restore must not hold the app pool on the target database."""
from unittest.mock import AsyncMock, patch

import pytest

from app.routers import backup as bk


def test_restore_stderr_transaction_timeout_is_not_fatal():
    stderr = (
        'pg_restore: error: could not execute query: ERROR:  '
        'unrecognized configuration parameter "transaction_timeout"\n'
        'pg_restore: warning: errors ignored on restore: 1\n'
    )
    assert bk.restore_stderr_is_fatal(stderr) is False


def test_restore_stderr_real_error_is_fatal():
    stderr = 'pg_restore: error: could not execute query: ERROR:  permission denied\n'
    assert bk.restore_stderr_is_fatal(stderr) is True


def test_terminate_backends_sql_excludes_self():
    sql = bk.terminate_backends_sql("cyberguard")
    assert "pg_terminate_backend" in sql
    assert "cyberguard" in sql
    assert "pid <> pg_backend_pid()" in sql


@pytest.mark.asyncio
async def test_run_psql_restore_uses_dump_file_not_stdin(monkeypatch):
    calls = {}

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            calls["stdin"] = input
            return b"", b""

    async def fake_exec(*cmd, **kwargs):
        calls["cmd"] = cmd
        calls["stdin_kw"] = kwargs.get("stdin")
        return _Proc()

    monkeypatch.setattr(bk.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(bk, "_disconnect_app_from_database", AsyncMock())
    await bk._run_psql_restore("/tmp/rc.dump")
    assert "/tmp/rc.dump" in calls["cmd"]
    assert calls["stdin"] is None


@pytest.mark.asyncio
async def test_disconnect_failure_is_not_silently_ignored(monkeypatch):
    class _Proc:
        returncode = 2

        async def communicate(self):
            return b"", b"permission denied"

    monkeypatch.setattr(bk.asyncio, "create_subprocess_exec", AsyncMock(return_value=_Proc()))
    monkeypatch.setattr("app.core.database.dispose_engines", AsyncMock())
    with pytest.raises(RuntimeError, match="permission denied"):
        await bk._disconnect_app_from_database()


def test_backup_manifest_snapshot_is_complete():
    record = bk.BackupRecordModel(
        id="b1", created_at=bk.datetime(2026, 9, 12), size_bytes=42,
        format="pg_dump.custom.aes", local_path="/backups/b1.dump.aes",
        remote_url=None, s3_bucket=None, status="completed", error=None,
        retention_days=30,
    )
    snapshot = bk._backup_manifest_snapshot(record)
    assert snapshot["id"] == "b1"
    assert snapshot["status"] == "completed"
    assert snapshot["local_path"] == "/backups/b1.dump.aes"
    assert snapshot["size_bytes"] == 42
