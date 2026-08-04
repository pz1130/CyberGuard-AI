"""M7: encrypted export, uninstall, update verify (INV-42), pack skeleton."""
from __future__ import annotations

import base64
import json
import os
import subprocess
from io import StringIO
from pathlib import Path

import pytest


@pytest.fixture
def m7_env(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    monkeypatch.setenv("CYBERGUARD_SESSION_ENCRYPTION", "0")
    yield root


def test_export_roundtrip_cgx1(m7_env, tmp_path):
    from apps.desktop.sidecar.sessions import SessionStore
    from apps.desktop.sidecar.export_bundle import (
        export_encrypted,
        decrypt_fernet_passphrase,
    )
    import tarfile
    import io

    store = SessionStore()
    meta = store.create(title="export-me", tier="readonly")
    store.append_event(meta.session_id, {"type": "note", "text": "secret-ish"})

    dest = tmp_path / "out.cgx"
    result = export_encrypted(
        dest,
        passphrase="test-passphrase-long",
        prefer_age=False,
        include=["sessions"],
    )
    assert result["ok"] is True
    assert result["method"] == "cgx1-fernet"
    assert dest.is_file()
    plain = decrypt_fernet_passphrase(dest.read_bytes(), "test-passphrase-long")
    # tar.gz
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
        names = tar.getnames()
    assert any("sessions" in n or n.endswith(".jsonl") or "export_manifest" in n for n in names)


def test_uninstall_dry_run_and_execute(m7_env):
    from apps.desktop.sidecar.sessions import SessionStore
    from apps.desktop.sidecar.uninstall import inventory, execute
    from apps.desktop.sidecar.paths import data_root

    SessionStore().create(title="x", tier="readonly")
    inv = inventory()
    assert inv["data_root"] == str(data_root())
    assert inv["will_delete"]
    assert "manual_steps" in inv

    dry = execute(confirm=True, dry_run=True)
    assert dry["executed"] is False
    assert data_root().is_dir()

    root_before = str(data_root())
    gone = execute(confirm=True, dry_run=False)
    assert gone["executed"] is True
    assert gone["ok"] is True
    assert any(root_before in d or d == root_before for d in gone.get("deleted") or [])
    # data_root() helper re-creates the directory on next call — that is OK


def test_update_rejects_tamper_downgrade_bad_sig(m7_env, monkeypatch):
    from apps.desktop.sidecar.update_verify import (
        UpdateVerifyError,
        generate_keypair,
        sign_manifest,
        verify_update,
        is_downgrade,
    )

    assert is_downgrade("1.2.0", "1.1.9") is True
    assert is_downgrade("1.2.0", "1.2.0") is False
    assert is_downgrade("1.2.0", "1.3.0") is False

    kp = generate_keypair()
    monkeypatch.setenv("CYBERGUARD_UPDATE_PUBKEY_B64", kp["public_b64"])

    artifact = b"fake-dmg-bytes"
    import hashlib

    sha = hashlib.sha256(artifact).hexdigest()
    manifest = {
        "product": "cyberguard-desktop",
        "version": "0.2.0",
        "channel": "stable",
        "artifact_sha256": sha,
    }
    manifest["signature"] = sign_manifest(manifest, kp["private_b64"])

    ok = verify_update(manifest, current_version="0.1.0", artifact_bytes=artifact)
    assert ok["ok"] is True

    # Tamper artifact
    with pytest.raises(UpdateVerifyError, match="sha256"):
        verify_update(
            manifest, current_version="0.1.0", artifact_bytes=b"tampered"
        )

    # Downgrade
    down = {
        "product": "cyberguard-desktop",
        "version": "0.0.9",
        "artifact_sha256": sha,
    }
    down["signature"] = sign_manifest(down, kp["private_b64"])
    with pytest.raises(UpdateVerifyError, match="downgrade"):
        verify_update(down, current_version="0.1.0", artifact_bytes=artifact)

    # Bad signature (wrong key)
    kp2 = generate_keypair()
    bad = dict(manifest)
    bad["signature"] = sign_manifest(bad, kp2["private_b64"])
    with pytest.raises(UpdateVerifyError, match="signature"):
        verify_update(bad, current_version="0.1.0", artifact_bytes=artifact)

    # MITM: flip version after signing
    mitm = dict(manifest)
    mitm["version"] = "9.9.9"
    with pytest.raises(UpdateVerifyError, match="signature"):
        verify_update(mitm, current_version="0.1.0", artifact_bytes=artifact)


@pytest.mark.asyncio
async def test_rpc_export_uninstall_update(m7_env, tmp_path, monkeypatch):
    from apps.desktop.sidecar.main import SidecarServer
    from apps.desktop.sidecar.sessions import SessionStore
    from apps.desktop.sidecar.update_verify import generate_keypair, sign_manifest
    import hashlib

    SessionStore().create(title="rpc", tier="readonly")

    async def rpc(method, params=None):
        out = StringIO()
        server = SidecarServer(StringIO(), out)
        await server.handle({"id": "1", "method": method, "params": params or {}})
        return json.loads(out.getvalue().strip().splitlines()[-1])

    dest = str(tmp_path / "e.cgx")
    msg = await rpc(
        "export.encrypted",
        {"dest_path": dest, "passphrase": "rpc-pass-word-ok", "include": ["sessions"]},
    )
    assert msg.get("result", {}).get("ok") is True

    msg = await rpc("uninstall.inventory", {})
    assert "will_delete" in msg["result"]

    kp = generate_keypair()
    monkeypatch.setenv("CYBERGUARD_UPDATE_PUBKEY_B64", kp["public_b64"])
    art = b"pkg"
    man = {
        "product": "cyberguard-desktop",
        "version": "0.3.0",
        "artifact_sha256": hashlib.sha256(art).hexdigest(),
    }
    man["signature"] = sign_manifest(man, kp["private_b64"])
    msg = await rpc(
        "update.verify",
        {
            "manifest": man,
            "current_version": "0.1.0",
            "artifact_b64": base64.b64encode(art).decode("ascii"),
        },
    )
    assert msg["result"]["ok"] is True

    # reject downgrade via RPC
    man2 = {
        "product": "cyberguard-desktop",
        "version": "0.0.1",
        "artifact_sha256": hashlib.sha256(art).hexdigest(),
    }
    man2["signature"] = sign_manifest(man2, kp["private_b64"])
    msg = await rpc(
        "update.verify",
        {"manifest": man2, "current_version": "0.2.0", "artifact_b64": base64.b64encode(art).decode()},
    )
    assert "error" in msg
    assert msg["error"]["code"] == "update_rejected"

    msg = await rpc("ping", {})
    assert msg["result"].get("m7") is True


def test_pack_check_skeleton_passes():
    """electron-builder skeleton + notarize dry-run without certs (M7)."""
    desktop = Path(__file__).resolve().parents[1] / "apps" / "desktop"
    script = desktop / "scripts" / "pack-check.sh"
    assert script.is_file()
    assert (desktop / "electron-builder.yml").is_file()
    assert (desktop / "scripts" / "notarize.cjs").is_file()
    assert (desktop / "entitlements" / "release.plist").is_file()
    yml = (desktop / "electron-builder.yml").read_text(encoding="utf-8")
    assert "appId: com.cyberguard.desktop" in yml
    assert "afterSign: scripts/notarize.cjs" in yml
    hook = (desktop / "scripts" / "notarize.cjs").read_text(encoding="utf-8")
    assert "DRY-RUN" in hook and "INV-38" in hook
    # Preload exposes export / uninstall UI bridge
    preload = (desktop / "electron" / "preload.cjs").read_text(encoding="utf-8")
    assert "exportEncrypted" in preload
    assert "uninstallInventory" in preload
    main = (desktop / "electron" / "main.cjs").read_text(encoding="utf-8")
    assert "sidecar:export:encrypted" in main
    assert "sidecar:uninstall:execute" in main
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(desktop),
        capture_output=True,
        text=True,
        env={**os.environ, "CYBERGUARD_NOTARIZE_DRY_RUN": "1"},
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "pack:check PASSED" in proc.stdout
