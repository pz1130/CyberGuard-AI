"""Session list recovers readable titles when index decrypt fails."""
from __future__ import annotations

import pytest

from apps.desktop.sidecar.sessions import SessionStore


@pytest.fixture
def sess_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    monkeypatch.setenv("CYBERGUARD_SESSION_ENCRYPTION", "1")
    return tmp_path / "cg"


def test_list_recovers_title_from_user_task(sess_env):
    store = SessionStore()
    meta = store.create(title="original-title", tier="readonly")
    store.append_event(
        meta.session_id,
        {"type": "user_task", "task": "调查 jump-01 上的 SSH 爆破"},
    )
    # Corrupt stored title so decrypt_title fails path triggers recovery
    import sqlite3
    from apps.desktop.sidecar.paths import session_index_db

    with sqlite3.connect(session_index_db()) as conn:
        conn.execute(
            "UPDATE sessions SET title = ? WHERE session_id = ?",
            ("enc1:gAAAAABcorrupted_token_not_valid_padding_xx", meta.session_id),
        )
        conn.commit()

    rows = store.list()
    match = next(r for r in rows if r.session_id == meta.session_id)
    assert "SSH" in match.title or "jump-01" in match.title
    assert not match.title.startswith("enc1:")
    assert match.title != "[encrypted title]"
