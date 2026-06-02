"""Tests for app.core.migrations (alembic startup helper)."""
from unittest.mock import patch, MagicMock

import pytest

from app.core.migrations import run_alembic_upgrade_on_startup, _Cmd


@pytest.fixture
def fake_run():
    """Subprocess.run that returns a MagicMock result; tests control returncode/stdout/stderr."""
    with patch("app.core.migrations.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield run


def test_calls_alembic_upgrade_head_first(fake_run):
    run_alembic_upgrade_on_startup()
    assert list(fake_run.call_args_list[0].args[0]) == list(_Cmd.upgrade_head)


def test_on_success_no_retry(fake_run):
    fake_run.return_value = MagicMock(returncode=0, stderr="")
    fake_run.return_value.returncode = 0
    out = run_alembic_upgrade_on_startup()
    assert out is True
    assert fake_run.call_count == 1


def test_on_multiple_heads_falls_back_to_each_head(fake_run):
    """Two head revisions in the project (#11 introduced a second head) — the
    upgrade-head call errors with 'Multiple head revisions', and we fall back to
    upgrading each head individually."""
    fake_run.side_effect = [
        MagicMock(returncode=1, stdout="FAILED: Multiple head revisions are present",
                  stderr="multiple heads"),
        MagicMock(returncode=0,
                  stdout="002b_create_document_chunks\n017_agent_episodes\n", stderr=""),
        MagicMock(returncode=0, stdout="running 002b", stderr=""),
        MagicMock(returncode=0, stdout="running 017", stderr=""),
    ]
    out = run_alembic_upgrade_on_startup()
    assert out is True
    cmds = [list(c.args[0]) for c in fake_run.call_args_list]
    assert list(_Cmd.upgrade_head) in cmds
    # Then one `alembic heads` (to discover the heads) + one upgrade per head
    assert list(_Cmd.heads) in cmds
    # And the per-head upgrades (one per discovered head)
    upgrade_calls = [c for c in cmds
                     if c[:3] == ["alembic", "-c", _Cmd.alembic_ini] and c[3] == "upgrade"
                     and c != list(_Cmd.upgrade_head)]
    assert len(upgrade_calls) == 2
    assert upgrade_calls[0][-1] == "002b_create_document_chunks"
    assert upgrade_calls[1][-1] == "017_agent_episodes"


def test_on_unrelated_failure_returns_false(fake_run):
    """A non-recoverable alembic error logs and returns False (don't crash boot)."""
    fake_run.return_value = MagicMock(returncode=1, stdout="boom",
                                       stderr="UndefinedTableError: x")
    out = run_alembic_upgrade_on_startup()
    assert out is False


def test_list_heads_strips_head_decoration():
    """`alembic heads` output looks like `'<rev> (head)'` — the suffix must
    be stripped so values can be passed back as `upgrade <rev>` arguments."""
    from app.core.migrations import _list_heads
    with patch("app.core.migrations._run") as run:
        run.return_value = MagicMock(returncode=0,
                                      stdout="002b_create_document_chunks (head)\n"
                                             "017_agent_episodes (head)\n",
                                      stderr="")
        assert _list_heads() == ["002b_create_document_chunks", "017_agent_episodes"]


def test_duplicate_table_falls_back_to_stamp(fake_run):
    """Existing-DB case: the table is already there → 'DuplicateTableError'/'already exists' → stamp head."""
    fake_run.side_effect = [
        MagicMock(returncode=1, stdout="FAILED",
                  stderr="DuplicateTableError: table already exists"),
        MagicMock(returncode=0, stdout="", stderr=""),
    ]
    out = run_alembic_upgrade_on_startup()
    assert out is True
    cmds = [list(c.args[0]) for c in fake_run.call_args_list]
    assert list(_Cmd.stamp_head) in cmds
