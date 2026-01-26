import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.core.auth import issue_session_token


def test_plan_week_returns_503_when_openai_missing() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.get("/plan/week", headers={"Authorization": f"Bearer {issue_session_token('u1')}"})
    assert r.status_code == 503


def test_chat_send_returns_503_when_openai_missing() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {issue_session_token('u1')}"},
        json={
            "user_message": "Hi",
            "current_plan": {"weekStart": "2026-01-13", "items": []},
        },
    )
    assert r.status_code == 503


