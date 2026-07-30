"""M1: session JSONL store, managed paths, MCP mock lifecycle."""
import os
import signal
import time
from pathlib import Path

import pytest

# Isolate data root before importing path-dependent modules
@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "cg-data"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    # Reload modules that cache nothing but call data_root() each time
    import importlib
    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.sessions as sessions
    importlib.reload(paths)
    importlib.reload(sessions)
    return root


def test_paths_under_managed_root(data_dir):
    from apps.desktop.sidecar.paths import (
        assert_under_data_root,
        data_root,
        managed_tempfile,
        sessions_dir,
        tmp_dir,
    )

    assert data_root() == data_dir.resolve()
    assert sessions_dir().is_relative_to(data_dir)
    assert tmp_dir().is_relative_to(data_dir)
    p = managed_tempfile(suffix=".txt")
    assert p.exists()
    assert_under_data_root(p)
    with pytest.raises(ValueError):
        assert_under_data_root(Path("/tmp/evil"))


def test_session_jsonl_roundtrip(data_dir):
    from apps.desktop.sidecar.sessions import SessionStore

    store = SessionStore()
    meta = store.create(title="Alert triage", tier="readonly")
    store.append_event(meta.session_id, {"type": "user_task", "task": "hi"})
    store.append_event(meta.session_id, {"type": "answer_ready", "candidate_text": "ok"})
    events = list(store.iter_events(meta.session_id))
    assert len(events) == 2
    assert events[0]["type"] == "user_task"
    listed = store.list()
    assert any(s.session_id == meta.session_id for s in listed)
    got = store.get_meta(meta.session_id)
    assert got and got.event_count == 2
    assert got.title == "Alert triage"


def test_mcp_mock_spawn_and_stop(data_dir):
    from apps.desktop.sidecar.mcp_manager import McpManager
    from apps.desktop.sidecar.process_group import ProcessRegistry

    reg = ProcessRegistry()
    # Don't setsid in tests (would detach pytest)
    mgr = McpManager()
    # Use module-level MCP? better fresh manager and register on REGISTRY
    from apps.desktop.sidecar import process_group as pg
    info = mgr.spawn_mock("t1", hold_seconds=30)
    assert info["pid"] > 0
    assert any(s["server_id"] == "t1" and s["alive"] for s in mgr.list())
    # Child should be alive
    os.kill(info["pid"], 0)
    assert mgr.stop("t1") is True
    time.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(info["pid"], 0)


def test_registry_kill_all_clears_children(data_dir):
    import subprocess
    import sys
    from apps.desktop.sidecar.process_group import ProcessRegistry

    reg = ProcessRegistry()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    reg.register(proc.pid, "test-child")
    reg.kill_all(sig=signal.SIGTERM)
    proc.wait(timeout=3)
    assert proc.poll() is not None
    assert reg.child_pids() == set()


@pytest.mark.asyncio
async def test_agent_run_persists_session(data_dir):
    from io import StringIO
    import json
    from apps.desktop.sidecar.main import SidecarServer
    from apps.desktop.sidecar.sessions import SessionStore

    stdin = StringIO()
    stdout = StringIO()
    server = SidecarServer(stdin, stdout)
    await server.handle(
        {
            "id": "r1",
            "method": "agent.run",
            "params": {"task": "persist me", "tier": "readonly"},
        }
    )
    lines = [json.loads(l) for l in stdout.getvalue().strip().splitlines() if l]
    result = next(m for m in lines if "result" in m and m.get("id") == "r1")
    sid = result["result"]["session_id"]
    store = SessionStore()
    events = list(store.iter_events(sid))
    assert any(e.get("type") == "user_task" for e in events)
    assert any(e.get("type") in ("answer_ready", "start", "run_started") for e in events)
