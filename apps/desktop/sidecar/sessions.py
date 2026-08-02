"""Local session store: tree-shaped JSONL + SQLite index.

M3: per-session Fernet encryption + crypto-shred delete (INV local-data).
Legacy plaintext JSONL remains readable when no encryption header is present.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from apps.desktop.sidecar.data_crypto import (
    SESSION_FILE_MAGIC,
    create_session_key,
    decrypt_text,
    decrypt_title,
    delete_session_key,
    encrypt_text,
    encrypt_title,
    encryption_enabled,
    get_session_key,
    has_session_key,
)
from apps.desktop.sidecar.paths import session_index_db, session_jsonl_path, sessions_dir

logger = logging.getLogger("cyberguard.desktop.sessions")

# Default body retention (design §5); overridable via env
DEFAULT_RETENTION_DAYS = 90


@dataclass
class SessionMeta:
    session_id: str
    title: str
    created_at: float
    updated_at: float
    tier: str
    event_count: int
    encrypted: bool = False


class SessionShreddedError(RuntimeError):
    """Body exists on disk but session key was destroyed (crypto-shred)."""


class SessionStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or session_index_db()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        sessions_dir()  # ensure parent exists
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'readonly',
                    event_count INTEGER NOT NULL DEFAULT 0,
                    encrypted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Migrate older DBs missing encrypted column
            cols = {
                r[1]
                for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "encrypted" not in cols:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN encrypted INTEGER NOT NULL DEFAULT 0"
                )
            conn.commit()

    def create(self, *, title: str = "Untitled", tier: str = "readonly") -> SessionMeta:
        sid = str(uuid.uuid4())
        now = time.time()
        path = session_jsonl_path(sid)
        path.parent.mkdir(parents=True, exist_ok=True)

        enc = encryption_enabled()
        if enc:
            create_session_key(sid)
            # Magic header marks encrypted file format
            path.write_text(SESSION_FILE_MAGIC, encoding="utf-8")
            stored_title = encrypt_title(title)
        else:
            path.touch(exist_ok=True)
            stored_title = title

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(session_id, title, created_at, updated_at, tier, event_count, encrypted) "
                "VALUES (?, ?, ?, ?, ?, 0, ?)",
                (sid, stored_title, now, now, tier, 1 if enc else 0),
            )
            conn.commit()
        return SessionMeta(sid, title, now, now, tier, 0, encrypted=enc)

    def list(self, limit: int = 50) -> List[SessionMeta]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: List[SessionMeta] = []
        for r in rows:
            enc = bool(r["encrypted"]) if "encrypted" in r.keys() else False
            out.append(
                SessionMeta(
                    r["session_id"],
                    decrypt_title(r["title"]),
                    r["created_at"],
                    r["updated_at"],
                    r["tier"],
                    r["event_count"],
                    encrypted=enc,
                )
            )
        return out

    def _is_encrypted_file(self, path: Path) -> bool:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            with path.open("r", encoding="utf-8") as f:
                first = f.readline()
            return first == SESSION_FILE_MAGIC or first.startswith("#CGSESS")
        except OSError:
            return False

    def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        path = session_jsonl_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)

        enc_file = self._is_encrypted_file(path)
        key = get_session_key(session_id) if encryption_enabled() else None

        if enc_file or (encryption_enabled() and key):
            if not key:
                # File claims encryption but key missing → shredded / unreadable
                raise SessionShreddedError(
                    f"session {session_id} key missing (crypto-shredded?)"
                )
            if not path.exists() or path.stat().st_size == 0:
                path.write_text(SESSION_FILE_MAGIC, encoding="utf-8")
            token = encrypt_text(key, line)
            with path.open("a", encoding="utf-8") as f:
                f.write(token + "\n")
            encrypted_flag = 1
        else:
            # Legacy plaintext
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            encrypted_flag = 0

        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ?, event_count = event_count + 1, "
                "encrypted = CASE WHEN encrypted = 1 OR ? = 1 THEN 1 ELSE encrypted END "
                "WHERE session_id = ?",
                (now, encrypted_flag, session_id),
            )
            if conn.total_changes == 0:
                title = encrypt_title("Recovered") if encryption_enabled() else "Recovered"
                if encryption_enabled() and not has_session_key(session_id):
                    create_session_key(session_id)
                conn.execute(
                    "INSERT OR IGNORE INTO sessions "
                    "(session_id, title, created_at, updated_at, tier, event_count, encrypted) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?)",
                    (
                        session_id,
                        title,
                        now,
                        now,
                        "readonly",
                        1 if encryption_enabled() else 0,
                    ),
                )
            conn.commit()

    def iter_events(self, session_id: str) -> Iterator[Dict[str, Any]]:
        path = session_jsonl_path(session_id)
        if not path.exists():
            return
        enc_file = self._is_encrypted_file(path)
        key = get_session_key(session_id) if enc_file else None
        if enc_file and not key:
            raise SessionShreddedError(
                f"session {session_id} body present but key destroyed (crypto-shred)"
            )

        with path.open("r", encoding="utf-8") as f:
            first = True
            for line in f:
                if first:
                    first = False
                    if line == SESSION_FILE_MAGIC or line.startswith("#CGSESS"):
                        continue
                line = line.strip()
                if not line:
                    continue
                if enc_file and key:
                    try:
                        plain = decrypt_text(key, line)
                    except Exception as exc:  # noqa: BLE001
                        raise SessionShreddedError(
                            f"session {session_id} decrypt failed"
                        ) from exc
                    yield json.loads(plain)
                else:
                    yield json.loads(line)

    def get_meta(self, session_id: str) -> Optional[SessionMeta]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not r:
            return None
        enc = bool(r["encrypted"]) if "encrypted" in r.keys() else False
        return SessionMeta(
            r["session_id"],
            decrypt_title(r["title"]),
            r["created_at"],
            r["updated_at"],
            r["tier"],
            r["event_count"],
            encrypted=enc,
        )

    def delete(self, session_id: str, *, crypto_shred: bool = True) -> Dict[str, Any]:
        """Delete session index + body. Crypto-shred = drop key first (default).

        After crypto-shred, residual ciphertext on disk (if unlink fails) is
        unreadable without the key. SSD wear-leveling means overwrite is not
        relied upon (design §4).
        """
        path = session_jsonl_path(session_id)
        key_deleted = False
        if crypto_shred:
            key_deleted = delete_session_key(session_id)

        file_removed = False
        if path.is_file():
            try:
                path.unlink()
                file_removed = True
            except OSError as exc:
                logger.warning("session file unlink failed: %s", type(exc).__name__)

        # If file remains after key delete, body is still unreadable
        unreadable = (not has_session_key(session_id)) and path.is_file()

        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

        return {
            "session_id": session_id,
            "crypto_shred": crypto_shred,
            "key_deleted": key_deleted or not has_session_key(session_id),
            "file_removed": file_removed,
            "body_unrecoverable": (not has_session_key(session_id)),
            "residual_ciphertext": unreadable,
        }

    def purge_expired(
        self, *, retention_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """Crypto-shred sessions older than retention (default 90d, design §5)."""
        days = retention_days
        if days is None:
            try:
                days = int(
                    os.environ.get("CYBERGUARD_SESSION_RETENTION_DAYS")
                    or DEFAULT_RETENTION_DAYS
                )
            except ValueError:
                days = DEFAULT_RETENTION_DAYS
        if days < 0:
            return {"purged": [], "retention_days": days, "skipped": True}

        cutoff = time.time() - (days * 86400)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE updated_at < ?",
                (cutoff,),
            ).fetchall()
        purged = []
        for r in rows:
            sid = r["session_id"]
            result = self.delete(sid, crypto_shred=True)
            purged.append(result)
        return {
            "purged": purged,
            "count": len(purged),
            "retention_days": days,
            "cutoff": cutoff,
        }
