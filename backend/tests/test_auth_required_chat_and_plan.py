import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_chat_send_returns_401_when_missing_token() -> None:
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.post("/chat/send", json={"user_message": "Hi"})
    assert r.status_code == 401


def test_plan_week_returns_401_when_missing_token() -> None:
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.get("/plan/week")
    assert r.status_code == 401


