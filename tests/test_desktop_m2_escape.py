"""M2 escape suite — explicit cases from roadmap exit criteria.

Run: pytest tests/test_desktop_m2_escape.py tests/test_desktop_m2_sandbox.py -q
"""
from __future__ import annotations

import platform
from pathlib import Path

import pytest

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.host_ops import ALLOWED_EXEC_BINARIES, HostOpsError
from apps.desktop.sidecar.policy import DualKnobPolicy
from apps.desktop.sidecar.sandbox import run_sandboxed
from apps.desktop.sidecar.sandbox.seatbelt import build_profile


requires_seatbelt = pytest.mark.skipif(
    platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="Seatbelt only on macOS with sandbox-exec",
)


def test_profile_read_only_denies_network():
    pol = DualKnobPolicy(sandbox_mode="read-only", approval_policy="on-request")
    text = build_profile(pol)
    assert "(deny network*)" in text
    assert "(deny file-write*)" in text


def test_profile_workspace_write_denies_network_by_default():
    pol = DualKnobPolicy(
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        writable_roots=("/tmp/ws",),
        network_access=False,
    )
    text = build_profile(pol)
    assert "(deny network*)" in text
    assert 'subpath "/tmp/ws"' in text or "subpath" in text


def test_profile_danger_full_refused():
    from apps.desktop.sidecar.sandbox import SeatbeltError

    pol = DualKnobPolicy(
        sandbox_mode="danger-full-access",
        approval_policy="never",
    )
    with pytest.raises(SeatbeltError):
        build_profile(pol)


def test_shell_and_curl_not_on_allowlist():
    assert "/bin/sh" not in ALLOWED_EXEC_BINARIES
    assert "/bin/bash" not in ALLOWED_EXEC_BINARIES
    assert "/usr/bin/curl" not in ALLOWED_EXEC_BINARIES
    assert "/usr/bin/nc" not in ALLOWED_EXEC_BINARIES
    assert "/usr/bin/python3" not in ALLOWED_EXEC_BINARIES


@requires_seatbelt
def test_escape_write_outside_writable_roots(tmp_path):
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
    bad = outside / "pwn.txt"
    r = run_sandboxed(
        ["/bin/sh", "-c", f"echo x > '{bad}'"],
        pol,
        profile_dir=tmp_path / "p",
        timeout_seconds=10,
    )
    # /bin/sh is used here only as escape *probe* at OS layer (not via host_run allowlist)
    assert not bad.exists(), f"escape write succeeded: {r}"


@requires_seatbelt
def test_escape_read_only_blocks_any_write(tmp_path):
    target = tmp_path / "nope.txt"
    pol = DualKnobPolicy(sandbox_mode="read-only", approval_policy="on-request")
    run_sandboxed(
        ["/bin/sh", "-c", f"echo x > '{target}'"],
        pol,
        profile_dir=tmp_path / "p",
        timeout_seconds=10,
    )
    assert not target.exists()


@pytest.mark.asyncio
@requires_seatbelt
async def test_escape_host_ops_blocks_outside_and_git(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("full")
    assert caps.real_edit is True
    outside = tmp_path / "escape.txt"
    with pytest.raises(HostOpsError):
        await caps.operations.edit.write_text(str(outside), "nope")
    # .git under workspace
    git_obj = Path(caps.policy.writable_roots[0]) / ".git" / "config"
    git_obj.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(HostOpsError) as ei:
        await caps.operations.edit.write_text(str(git_obj), "hack")
    assert ".git" in str(ei.value).lower()


@pytest.mark.asyncio
@requires_seatbelt
async def test_escape_credential_path_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("readonly")
    secret = tmp_path / "cg" / "provider.json"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('{"api_key":"sk-test"}', encoding="utf-8")
    with pytest.raises(HostOpsError):
        await caps.operations.read.read_text(str(secret))


@pytest.mark.asyncio
@requires_seatbelt
async def test_escape_exec_disallows_shell_and_network_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("full")
    assert caps.real_exec is True
    with pytest.raises(HostOpsError):
        await caps.operations.exec.run(["/bin/sh", "-c", "curl http://127.0.0.1"])
    with pytest.raises(HostOpsError):
        await caps.operations.exec.run(["/usr/bin/curl", "https://example.com"])
    # allowlisted binary still works
    r = await caps.operations.exec.run(["/usr/bin/uname"])
    assert int(r.get("exit_code", 1)) == 0


@pytest.mark.asyncio
async def test_escape_readonly_tier_no_exec_edit_ports(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    caps = capabilities_for_tier("readonly")
    assert caps.operations.exec is None
    assert caps.operations.edit is None
    assert caps.real_exec is False
    assert caps.real_edit is False


@pytest.mark.asyncio
async def test_sandbox_none_denies_real_host_io(monkeypatch, tmp_path):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setattr(
        "apps.desktop.sidecar.host_ops.detect_sandbox_impl",
        lambda: "none",
    )
    monkeypatch.setattr(
        "apps.desktop.sidecar.capabilities.detect_sandbox_impl",
        lambda: "none",
    )
    # rebuild ops path
    from apps.desktop.sidecar.host_ops import build_read_operations, build_exec_operations
    from apps.desktop.sidecar.policy import policy_for_tier

    pol = policy_for_tier("full", workspace_root=str(tmp_path / "ws"), managed_tmp=str(tmp_path / "t"))
    read_ops, real_r = build_read_operations(pol, data_root=str(tmp_path / "cg"))
    exec_ops, real_e = build_exec_operations(pol, data_root=str(tmp_path / "cg"))
    assert real_r is False
    assert real_e is False
    with pytest.raises(Exception):
        await read_ops.read_text("/etc/hosts")
    with pytest.raises(Exception):
        await exec_ops.run(["/usr/bin/uname"])
