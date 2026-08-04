"""M2: dual-knob policy + macOS Seatbelt escape suite + sandboxed read."""
from __future__ import annotations

import platform
from pathlib import Path

import pytest

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.policy import DualKnobPolicy, policy_for_tier
from apps.desktop.sidecar.sandbox import (
    SeatbeltError,
    build_profile,
    detect_sandbox_impl,
    run_sandboxed,
    sandbox_public_status,
)


def test_policy_readonly_has_no_writable_roots():
    p = policy_for_tier("readonly", workspace_root="/ws", managed_tmp="/tmp-m")
    assert p.sandbox_mode == "read-only"
    assert p.writable_roots == ()
    assert p.network_access is False
    assert p.approval_policy == "on-request"


def test_policy_full_workspace_write_roots():
    p = policy_for_tier("full", workspace_root="/ws", managed_tmp="/tmp-m")
    assert p.sandbox_mode == "workspace-write"
    assert "/ws" in p.writable_roots
    assert "/tmp-m" in p.writable_roots
    assert p.network_access is False


def test_always_readonly_paths_are_subdirs_not_whole_root():
    from apps.desktop.sidecar.policy import always_readonly_paths

    paths = always_readonly_paths("/data/cg")
    assert any(p.endswith("sessions") for p in paths)
    assert any(p.endswith("evidence") for p in paths)
    assert any(p.endswith("secrets") for p in paths)
    assert any(p.endswith("config") for p in paths)
    assert any(p.endswith("audit") for p in paths)
    assert "/data/cg" not in paths  # whole root must not be blanket-protected


def test_capabilities_readonly_still_no_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("readonly")
    assert caps.operations.exec is None
    assert caps.operations.edit is None
    d = caps.describe()
    assert d["has_exec"] is False
    assert d["policy"]["sandbox_mode"] == "read-only"
    assert "sandbox_impl" in d


def test_capabilities_full_declares_workspace_write(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("full")
    assert caps.policy.sandbox_mode == "workspace-write"
    # Exec/edit still mock; read is real when seatbelt is available
    assert caps.operations.exec is not None
    if detect_sandbox_impl() == "seatbelt":
        assert caps.real_read is True
        assert caps.describe()["real_read"] is True
        assert caps.describe()["mock"] is False
    else:
        assert caps.real_read is False


def test_detect_sandbox_impl_on_macos():
    impl = detect_sandbox_impl()
    if platform.system() == "Darwin" and Path("/usr/bin/sandbox-exec").is_file():
        assert impl == "seatbelt"
    else:
        assert impl == "none"
    status = sandbox_public_status()
    assert status["sandbox_impl"] == impl


def test_danger_full_access_profile_refused():
    pol = DualKnobPolicy(
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )
    with pytest.raises(SeatbeltError):
        build_profile(pol)


def test_read_only_profile_denies_network_token():
    pol = DualKnobPolicy(sandbox_mode="read-only", approval_policy="on-request")
    text = build_profile(pol)
    assert "(deny network*)" in text
    assert "danger" not in text


@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
def test_seatbelt_read_only_blocks_write_outside(tmp_path):
    """Escape case: read-only profile must not write a file in tmp_path."""
    target = tmp_path / "should-not-exist.txt"
    pol = DualKnobPolicy(sandbox_mode="read-only", approval_policy="on-request")
    # Use /bin/sh -c to attempt a write
    result = run_sandboxed(
        ["/bin/sh", "-c", f"echo pwned > '{target}'"],
        pol,
        profile_dir=tmp_path / "profiles",
        timeout_seconds=10,
    )
    assert result["sandboxed"] is True
    # Either non-zero exit or file not created
    assert (not target.exists()) or result["exit_code"] != 0
    assert not target.exists(), "read-only sandbox must block write"


@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
def test_seatbelt_workspace_write_allows_root_blocks_outside(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    pol = DualKnobPolicy(
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        writable_roots=(str(allowed),),
        network_access=False,
    )
    ok_file = allowed / "ok.txt"
    bad_file = outside / "bad.txt"
    r_ok = run_sandboxed(
        ["/bin/sh", "-c", f"echo yes > '{ok_file}'"],
        pol,
        profile_dir=tmp_path / "profiles-ok",
        timeout_seconds=10,
    )
    r_bad = run_sandboxed(
        ["/bin/sh", "-c", f"echo no > '{bad_file}'"],
        pol,
        profile_dir=tmp_path / "profiles-bad",
        timeout_seconds=10,
    )
    assert ok_file.exists(), f"write inside root should work: {r_ok}"
    assert not bad_file.exists(), f"write outside root must fail: {r_bad}"


@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
def test_seatbelt_workspace_write_protects_data_root(tmp_path):
    """Even under workspace-write, protective paths must stay read-only."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    protected = tmp_path / "ws" / "sensitive"
    protected.mkdir()
    pol = DualKnobPolicy(
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        writable_roots=(str(workspace),),
        network_access=False,
    )
    victim = protected / "policy.json"
    result = run_sandboxed(
        ["/bin/sh", "-c", f"echo hacked > '{victim}'"],
        pol,
        readonly_paths=(str(protected),),
        profile_dir=tmp_path / "profiles-prot",
        timeout_seconds=10,
    )
    assert not victim.exists(), f"protected subpath must deny write: {result}"


@pytest.mark.asyncio
@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
async def test_sandboxed_read_operations_reads_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    sample = tmp_path / "sample.txt"
    sample.write_text("hello-m2-read\nsecond-line\n", encoding="utf-8")
    caps = capabilities_for_tier("readonly")
    assert caps.real_read is True
    assert caps.operations.exec is None
    text = await caps.operations.read.read_text(str(sample), max_bytes=1000)
    assert "hello-m2-read" in text
    names = await caps.operations.read.list_dir(str(tmp_path))
    assert "sample.txt" in names


@pytest.mark.asyncio
@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
async def test_sandboxed_read_blocks_provider_json(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    secret = tmp_path / "cg" / "provider.json"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('{"api_key":"sk-secret"}', encoding="utf-8")
    caps = capabilities_for_tier("readonly")
    with pytest.raises(Exception) as ei:
        await caps.operations.read.read_text(str(secret))
    assert "blocked" in str(ei.value).lower() or "denied" in str(ei.value).lower()


@pytest.mark.asyncio
async def test_capabilities_real_read_when_seatbelt(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    sample = tmp_path / "note.txt"
    sample.write_text("agent-host-read-ok", encoding="utf-8")
    caps = capabilities_for_tier("readonly")
    if detect_sandbox_impl() == "seatbelt":
        assert caps.real_read is True
        text = await caps.operations.read.read_text(str(sample))
        assert "agent-host-read-ok" in text
    else:
        assert caps.real_read is False


@pytest.mark.asyncio
@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
async def test_sandboxed_write_in_workspace_only(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("full")
    assert caps.real_edit is True
    assert caps.policy.sandbox_mode == "workspace-write"
    ws = Path(caps.policy.writable_roots[0])
    target = ws / "notes" / "m2-write.txt"
    await caps.operations.edit.write_text(str(target), "workspace-write-ok\n")
    assert target.read_text(encoding="utf-8") == "workspace-write-ok\n"
    # re-read via sandboxed read
    text = await caps.operations.read.read_text(str(target))
    assert "workspace-write-ok" in text
    # outside workspace denied
    outside = tmp_path / "outside.txt"
    with pytest.raises(Exception) as ei:
        await caps.operations.edit.write_text(str(outside), "nope")
    assert "writable" in str(ei.value).lower() or "outside" in str(ei.value).lower()
    # sessions dir protected
    sess = Path(tmp_path / "cg" / "sessions" / "evil.jsonl")
    sess.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(Exception):
        await caps.operations.edit.write_text(str(sess), "hack")
    await caps.operations.edit.delete(str(target))
    assert not target.exists()


@pytest.mark.asyncio
async def test_readonly_tier_cannot_write(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("readonly")
    assert caps.operations.edit is None
    assert caps.real_edit is False


@pytest.mark.asyncio
@pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)
async def test_sandboxed_exec_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("full")
    assert caps.real_exec is True
    r = await caps.operations.exec.run(["/usr/bin/uname", "-s"])
    assert r.get("sandboxed") is True
    assert r.get("mock") is False
    assert int(r.get("exit_code", 1)) == 0
    assert "Darwin" in str(r.get("stdout") or "")
    # shell / non-allowlisted binary denied
    with pytest.raises(Exception) as ei:
        await caps.operations.exec.run(["/bin/sh", "-c", "echo pwned"])
    assert "allowlist" in str(ei.value).lower() or "binary" in str(ei.value).lower()
    with pytest.raises(Exception):
        await caps.operations.exec.run(["echo", "no-absolute"])


@pytest.mark.asyncio
async def test_readonly_has_no_exec_port(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("readonly")
    assert caps.operations.exec is None
    assert caps.real_exec is False
