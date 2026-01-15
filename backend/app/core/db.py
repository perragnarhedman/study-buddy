from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from app.core.config import get_settings


def get_conn() -> sqlite3.Connection:
    settings = get_settings()
    path = Path(settings.sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
          user_id TEXT PRIMARY KEY,
          access_token TEXT NOT NULL,
          refresh_token TEXT,
          expires_at INTEGER,
          token_type TEXT,
          scope TEXT,
          id_token TEXT
        )
        """
    )
    conn.commit()


def upsert_tokens(
    *,
    user_id: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at: Optional[int],
    token_type: Optional[str],
    scope: Optional[str],
    id_token: Optional[str],
) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO oauth_tokens (user_id, access_token, refresh_token, expires_at, token_type, scope, id_token)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              access_token=excluded.access_token,
              refresh_token=COALESCE(excluded.refresh_token, oauth_tokens.refresh_token),
              expires_at=excluded.expires_at,
              token_type=excluded.token_type,
              scope=excluded.scope,
              id_token=excluded.id_token
            """,
            (user_id, access_token, refresh_token, expires_at, token_type, scope, id_token),
        )


def get_tokens(user_id: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM oauth_tokens WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


