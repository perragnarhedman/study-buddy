import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app


def test_chat_send_returns_400_when_current_plan_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post("/chat/send", headers={"Authorization": f"Bearer {token}"}, json={"user_message": "Hi"})
    assert r.status_code == 400


