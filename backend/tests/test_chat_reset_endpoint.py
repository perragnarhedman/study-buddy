import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app


def test_chat_reset_clears_history_and_summary(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import append_chat_history, get_chat_history, get_user_state, upsert_user_state

    append_chat_history(user_id="u1", role="user", text="hello", created_at=1)
    append_chat_history(user_id="u1", role="assistant", text="hi", created_at=2)
    upsert_user_state(user_id="u1", conversation_summary="U: hello\nA: hi", updated_at=2)

    assert get_chat_history(user_id="u1", limit=10)
    assert get_user_state(user_id="u1").get("conversation_summary")

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post("/chat/reset", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

    assert get_chat_history(user_id="u1", limit=10) == []
    assert "conversation_summary" not in get_user_state(user_id="u1")


