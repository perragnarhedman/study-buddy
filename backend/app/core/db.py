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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_status (
          user_id TEXT NOT NULL,
          source_assignment_id TEXT NOT NULL,
          status TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY (user_id, source_assignment_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
          user_id TEXT NOT NULL,
          role TEXT NOT NULL,
          text TEXT NOT NULL,
          created_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_state (
          user_id TEXT PRIMARY KEY,
          last_selected_plan_item_id TEXT,
          last_selected_assignment_id TEXT,
          language_preference TEXT,
          last_intent TEXT,
          preferred_subject TEXT,
          conversation_summary TEXT,
          updated_at INTEGER NOT NULL
        )
        """
    )
    # Lightweight migrations for existing DBs.
    _ensure_column(conn, "user_state", "last_selected_assignment_id", "TEXT")
    _ensure_column(conn, "user_state", "language_preference", "TEXT")
    _ensure_column(conn, "user_state", "last_intent", "TEXT")
    _ensure_column(conn, "user_state", "preferred_subject", "TEXT")
    _ensure_column(conn, "user_state", "conversation_summary", "TEXT")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, col_type: str) -> None:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows}  # 2nd field is name
        if col in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
    except Exception:
        # Best-effort only.
        return


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


def set_assignment_status(*, user_id: str, source_assignment_id: str, status: str, updated_at: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO assignment_status (user_id, source_assignment_id, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, source_assignment_id) DO UPDATE SET
              status=excluded.status,
              updated_at=excluded.updated_at
            """,
            (user_id, source_assignment_id, status, updated_at),
        )


def get_assignment_status_map(*, user_id: str) -> dict[str, str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT source_assignment_id, status FROM assignment_status WHERE user_id=?",
        (user_id,),
    ).fetchall()
    return {str(r["source_assignment_id"]): str(r["status"]) for r in rows}


def append_chat_history(*, user_id: str, role: str, text: str, created_at: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, text, created_at),
        )
        # Keep last 20 rows per user (simple pruning).
        conn.execute(
            """
            DELETE FROM chat_history
            WHERE rowid IN (
              SELECT rowid FROM chat_history
              WHERE user_id=?
              ORDER BY created_at DESC
              LIMIT -1 OFFSET 20
            )
            """,
            (user_id,),
        )


def get_chat_history(*, user_id: str, limit: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT role, text, created_at
        FROM chat_history
        WHERE user_id=?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (user_id, int(limit)),
    ).fetchall()
    return [{"role": str(r["role"]), "text": str(r["text"]), "created_at": int(r["created_at"])} for r in rows]


def set_last_selected_plan_item_id(*, user_id: str, plan_item_id: str, updated_at: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO user_state (user_id, last_selected_plan_item_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              last_selected_plan_item_id=excluded.last_selected_plan_item_id,
              updated_at=excluded.updated_at
            """,
            (user_id, plan_item_id, updated_at),
        )


def set_last_selected_assignment_id(*, user_id: str, assignment_id: str, updated_at: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO user_state (user_id, last_selected_assignment_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              last_selected_assignment_id=excluded.last_selected_assignment_id,
              updated_at=excluded.updated_at
            """,
            (user_id, assignment_id, updated_at),
        )


def get_last_selected_assignment_id(*, user_id: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_selected_assignment_id FROM user_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    v = row["last_selected_assignment_id"]
    return str(v) if isinstance(v, str) and v else None


def get_last_selected_plan_item_id(*, user_id: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_selected_plan_item_id FROM user_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    v = row["last_selected_plan_item_id"]
    return str(v) if isinstance(v, str) and v else None


def get_user_state(*, user_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_selected_plan_item_id, last_selected_assignment_id, language_preference, last_intent, preferred_subject, conversation_summary FROM user_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if not row:
        return {}
    out = {
        "last_selected_plan_item_id": row["last_selected_plan_item_id"],
        "last_selected_assignment_id": row["last_selected_assignment_id"],
        "language_preference": row["language_preference"],
        "last_intent": row["last_intent"],
        "preferred_subject": row["preferred_subject"],
        "conversation_summary": row["conversation_summary"],
    }
    return {k: v for k, v in out.items() if v is not None and v != ""}


def upsert_user_state(
    *,
    user_id: str,
    language_preference: Optional[str] = None,
    last_intent: Optional[str] = None,
    preferred_subject: Optional[str] = None,
    conversation_summary: Optional[str] = None,
    updated_at: int,
) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO user_state (user_id, last_selected_plan_item_id, language_preference, last_intent, preferred_subject, conversation_summary, updated_at)
            VALUES (?, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              language_preference=COALESCE(excluded.language_preference, user_state.language_preference),
              last_intent=COALESCE(excluded.last_intent, user_state.last_intent),
              preferred_subject=COALESCE(excluded.preferred_subject, user_state.preferred_subject),
              conversation_summary=COALESCE(excluded.conversation_summary, user_state.conversation_summary),
              updated_at=excluded.updated_at
            """,
            (user_id, language_preference, last_intent, preferred_subject, conversation_summary, updated_at),
        )


