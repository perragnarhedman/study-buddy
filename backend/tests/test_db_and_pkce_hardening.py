import os
import sqlite3
from pathlib import Path

import pytest

from app.core import db as db_module
from app.core.config import get_settings
from app.services.pkce_store import PKCEStore


def _set_sqlite_path(tmp_path: Path) -> None:
    os.environ["SQLITE_PATH"] = str(tmp_path / "test.sqlite3")
    get_settings.cache_clear()


def test_db_conn_context_manager_closes_connection(tmp_path: Path) -> None:
    _set_sqlite_path(tmp_path)
    with db_module.db_conn() as conn:
        conn.execute("SELECT 1").fetchone()

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1").fetchone()


def test_db_pragmas_and_indexes_present(tmp_path: Path) -> None:
    _set_sqlite_path(tmp_path)
    with db_module.db_conn() as conn:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        idx_rows = conn.execute("PRAGMA index_list('chat_history')").fetchall()

    assert busy_timeout >= 10_000
    # sqlite PRAGMA synchronous=NORMAL typically reports integer 1.
    assert int(synchronous) == 1
    index_names = {str(r[1]) for r in idx_rows}
    assert "idx_chat_history_user_created" in index_names


def test_pkce_store_has_expiry_and_replay_protection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sqlite_path(tmp_path)
    store = PKCEStore(ttl_seconds=60)

    now = {"value": 1000.0}
    monkeypatch.setattr(db_module.time, "time", lambda: now["value"])

    store.put("state-1", "verifier-1")
    assert store.pop("state-1") == "verifier-1"
    assert store.pop("state-1") is None


def test_pkce_store_expires_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sqlite_path(tmp_path)
    store = PKCEStore(ttl_seconds=5)

    now = {"value": 100.0}
    monkeypatch.setattr(db_module.time, "time", lambda: now["value"])
    store.put("state-2", "verifier-2")
    now["value"] = 107.0

    assert store.pop("state-2") is None

