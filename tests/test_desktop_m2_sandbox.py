"""M2: dual-knob policy + macOS Seatbelt escape suite (first slice)."""
from __future__ import annotations

import os
import platform
import shutil
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
    # Host tools remain mock until real Operations wire-up
    assert caps.describe()["mock"] is True


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
