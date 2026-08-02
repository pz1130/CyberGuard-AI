"""M3: session encryption, crypto-shred, backup exclusion."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "cg-data"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    monkeypatch.setenv("CYBERGUARD_SESSION_ENCRYPTION", "1")
    # Fresh modules that read env
    import importlib

    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.secrets_store as secrets_store
    import apps.desktop.sidecar.data_crypto as data_crypto
    import apps.desktop.sidecar.sessions as sessions
    import apps.desktop.sidecar.backup_exclude as backup_exclude

    importlib.reload(paths)
    importlib.reload(secrets_store)
    importlib.reload(data_crypto)
    importlib.reload(sessions)
    importlib.reload(backup_exclude)
    return root


def test_encrypted_session_roundtrip(data_dir):
    from apps.desktop.sidecar.sessions import SessionStore
    from apps.desktop.sidecar.paths import session_jsonl_path
    from apps.desktop.sidecar.data_crypto import has_session_key

    store = SessionStore()
    meta = store.create(title="Acme breach investigation", tier="readonly")
    assert meta.encrypted is True
    assert has_session_key(meta.session_id)

    store.append_event(meta.session_id, {"type": "user_task", "task": "secret findings"})
    store.append_event(
        meta.session_id, {"type": "answer_ready", "candidate_text": "do not leak"}
    )

    # On-disk file must not contain plaintext secrets
    raw = session_jsonl_path(meta.session_id).read_text(encoding="utf-8")
    assert "secret findings" not in raw
    assert "do not leak" not in raw
    assert "Acme breach" not in raw
    assert raw.startswith("#CGSESS")

    events = list(store.iter_events(meta.session_id))
    assert len(events) == 2
    assert events[0]["task"] == "secret findings"

    listed = store.list()
    assert any(s.title == "Acme breach investigation" for s in listed)


def test_crypto_shred_makes_body_unrecoverable(data_dir):
    from apps.desktop.sidecar.sessions import SessionStore, SessionShreddedError
    from apps.desktop.sidecar.paths import session_jsonl_path
    from apps.desktop.sidecar.data_crypto import (
        delete_session_key,
        has_session_key,
        get_session_key,
    )

    store = SessionStore()
    meta = store.create(title="shred-me", tier="full")
    store.append_event(meta.session_id, {"type": "note", "text": "TOP SECRET BODY"})
    path = session_jsonl_path(meta.session_id)
    # Force residual ciphertext: delete key first, keep file
    assert has_session_key(meta.session_id)
    ciphertext = path.read_bytes()
    assert b"TOP SECRET BODY" not in ciphertext

    result = store.delete(meta.session_id, crypto_shred=True)
    assert result["body_unrecoverable"] is True
    assert not has_session_key(meta.session_id)
    assert store.get_meta(meta.session_id) is None

    # Even if attacker recovers residual file from disk image, no key → unreadable
    # Re-create file with old ciphertext and assert shred error
    path.write_bytes(ciphertext)
    with pytest.raises(SessionShreddedError):
        list(store.iter_events(meta.session_id))
    assert get_session_key(meta.session_id) is None


def test_crypto_shred_key_only_without_unlink(data_dir, monkeypatch):
    """If unlink fails, key drop alone still shreds."""
    from apps.desktop.sidecar import sessions as sessions_mod
    from apps.desktop.sidecar.sessions import SessionStore, SessionShreddedError
    from apps.desktop.sidecar.data_crypto import has_session_key

    store = SessionStore()
    meta = store.create(title="x", tier="readonly")
    store.append_event(meta.session_id, {"type": "a", "v": 1})

    real_unlink = Path.unlink

    def boom(self, *a, **k):
        raise OSError("simulated")

    monkeypatch.setattr(Path, "unlink", boom)
    result = store.delete(meta.session_id, crypto_shred=True)
    monkeypatch.setattr(Path, "unlink", real_unlink)

    assert result["key_deleted"] or result["body_unrecoverable"]
    assert not has_session_key(meta.session_id)
    assert result["residual_ciphertext"] is True or result["file_removed"] is False
    with pytest.raises(SessionShreddedError):
        list(store.iter_events(meta.session_id))


def test_purge_expired(data_dir):
    from apps.desktop.sidecar.sessions import SessionStore
    import time

    store = SessionStore()
    old = store.create(title="old", tier="readonly")
    store.append_event(old.session_id, {"type": "x"})
    # backdate
    with store._connect() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (time.time() - 100 * 86400, old.session_id),
        )
        conn.commit()
    fresh = store.create(title="fresh", tier="readonly")
    out = store.purge_expired(retention_days=90)
    assert out["count"] >= 1
    assert store.get_meta(old.session_id) is None
    assert store.get_meta(fresh.session_id) is not None


def test_backup_exclude_markers(data_dir):
    from apps.desktop.sidecar.backup_exclude import apply_exclusions, public_status, MARKER_NAME
    from apps.desktop.sidecar.paths import sessions_dir, episodic_dir, tmp_dir

    result = apply_exclusions()
    assert result["dirs"]
    for d in (sessions_dir(), episodic_dir(), tmp_dir()):
        assert (d / MARKER_NAME).is_file()
    st = public_status()
    assert any(x["marker"] for x in st["excluded_dirs"])


def test_plaintext_opt_out(data_dir, monkeypatch, tmp_path):
    root = tmp_path / "plain"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    monkeypatch.setenv("CYBERGUARD_SESSION_ENCRYPTION", "0")
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    import importlib
    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.secrets_store as secrets_store
    import apps.desktop.sidecar.data_crypto as data_crypto
    import apps.desktop.sidecar.sessions as sessions

    importlib.reload(paths)
    importlib.reload(secrets_store)
    importlib.reload(data_crypto)
    importlib.reload(sessions)

    store = sessions.SessionStore()
    meta = store.create(title="plain-title", tier="readonly")
    assert meta.encrypted is False
    store.append_event(meta.session_id, {"type": "user_task", "task": "visible"})
    raw = paths.session_jsonl_path(meta.session_id).read_text(encoding="utf-8")
    assert "visible" in raw


def test_encryption_status_claims_honest(data_dir):
    from apps.desktop.sidecar.data_crypto import public_status

    st = public_status()
    assert st["session_encryption"] is True
    assert "FileVault" in st["claims"] or "filevault" in st["claims"].lower() or "replace" in st["claims"].lower()
