"""Local session store: tree-shaped JSONL + SQLite index (M1 skeleton).

M1: plaintext under managed data root (encryption is M3). No system /tmp.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from apps.desktop.sidecar.paths import session_index_db, session_jsonl_path, sessions_dir


@dataclass
class SessionMeta:
    session_id: str
    title: str
    created_at: float
    updated_at: float
    tier: str
    event_count: int


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
                    event_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def create(self, *, title: str = "Untitled", tier: str = "readonly") -> SessionMeta:
        sid = str(uuid.uuid4())
        now = time.time()
        path = session_jsonl_path(sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, created_at, updated_at, tier, event_count) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (sid, title, now, now, tier),
            )
            conn.commit()
        return SessionMeta(sid, title, now, now, tier, 0)

    def list(self, limit: int = 50) -> List[SessionMeta]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            SessionMeta(
                r["session_id"],
                r["title"],
                r["created_at"],
                r["updated_at"],
                r["tier"],
                r["event_count"],
            )
            for r in rows
        ]

    def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        path = session_jsonl_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ?, event_count = event_count + 1 "
                "WHERE session_id = ?",
                (now, session_id),
            )
            # Auto-create index row if missing (defensive)
            if conn.total_changes == 0:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions "
                    "(session_id, title, created_at, updated_at, tier, event_count) "
                    "VALUES (?, ?, ?, ?, ?, 1)",
                    (session_id, "Recovered", now, now, "readonly"),
                )
            conn.commit()

    def iter_events(self, session_id: str) -> Iterator[Dict[str, Any]]:
        path = session_jsonl_path(session_id)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def get_meta(self, session_id: str) -> Optional[SessionMeta]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not r:
            return None
        return SessionMeta(
            r["session_id"],
            r["title"],
            r["created_at"],
            r["updated_at"],
            r["tier"],
            r["event_count"],
        )
