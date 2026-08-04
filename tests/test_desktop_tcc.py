"""TCC probe unit tests (macOS heuristic; non-mac returns supported=False)."""
from __future__ import annotations

import platform
from pathlib import Path
from unittest import mock

import pytest

from apps.desktop.sidecar.tcc import tcc_status, _probe_listable, _probe_readable_file


def test_tcc_status_shape():
    st = tcc_status()
    assert "supported" in st
    assert "summary" in st
    assert "locations" in st
    assert "warning" in st
    assert "guidance" in st
    if platform.system() != "Darwin":
        assert st["supported"] is False
        assert st["summary"] == "not_macos"
    else:
        assert st["supported"] is True
        assert st["summary"] in ("fda_likely", "restricted", "unknown")
        assert isinstance(st["locations"], list)
        assert len(st["locations"]) >= 3


def test_probe_listable_missing(tmp_path):
    ok, detail = _probe_listable(tmp_path / "no-such-dir")
    assert ok is True
    assert detail == "missing"


def test_probe_listable_ok(tmp_path):
    d = tmp_path / "desk"
    d.mkdir()
    (d / "a.txt").write_text("x", encoding="utf-8")
    ok, detail = _probe_listable(d)
    assert ok is True
    assert detail is None


def test_probe_file_permission_denied(tmp_path):
    f = tmp_path / "secret"
    f.write_text("x", encoding="utf-8")
    with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
        ok, detail = _probe_readable_file(f)
    assert ok is False
    assert detail == "permission_denied"


def test_tcc_restricted_when_desktop_blocked(monkeypatch):
    if platform.system() != "Darwin":
        pytest.skip("macOS-only heuristic paths")

    def fake_listable(path: Path):
        if path.name == "Desktop":
            return False, "permission_denied"
        if not path.exists():
            return True, "missing"
        return True, None

    def fake_file(path: Path):
        return True, "missing"

    monkeypatch.setattr("apps.desktop.sidecar.tcc._probe_listable", fake_listable)
    monkeypatch.setattr("apps.desktop.sidecar.tcc._probe_readable_file", fake_file)
    st = tcc_status()
    assert st["summary"] == "restricted"
    assert st["warning"]
    assert "Desktop" in st["warning"] or "desktop" in st["warning"].lower()
    assert st["guidance"]


@pytest.mark.asyncio
async def test_ping_includes_tcc(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    from io import StringIO
    import json
    from apps.desktop.sidecar.main import SidecarServer

    stdin = StringIO()
    stdout = StringIO()
    server = SidecarServer(stdin, stdout)
    await server.handle({"id": "1", "method": "ping", "params": {}})
    msg = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert msg["result"]["ok"] is True
    assert "tcc" in msg["result"]
    assert "summary" in msg["result"]["tcc"]
