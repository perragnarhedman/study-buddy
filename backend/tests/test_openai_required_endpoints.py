import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_plan_week_returns_503_when_openai_missing() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.get("/plan/week")
    assert r.status_code == 503


def test_chat_send_returns_503_when_openai_missing() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.post("/chat/send", json={"user_message": "Hi"})
    assert r.status_code == 503


