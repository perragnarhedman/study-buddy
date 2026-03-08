import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_chat_send_returns_401_when_missing_token() -> None:
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.post("/chat/send", json={"user_message": "Hi"})
    assert r.status_code == 401


def test_chat_send_intro_succeeds_without_token(monkeypatch) -> None:
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_intro_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="Hi! I can explain what Study Buddy does.",
            reply_language="en",
        )

    monkeypatch.setattr(chat_route, "intro_decide", fake_intro_decide)

    client = TestClient(app)
    r = client.post(
        "/chat/send",
        json={"user_message": "Hi", "chat_mode": "intro"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["assistant_message"]["text"] == "Hi! I can explain what Study Buddy does."
    assert body["best_next_action"] is None


def test_plan_week_returns_401_when_missing_token() -> None:
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()
    client = TestClient(app)
    r = client.get("/plan/week")
    assert r.status_code == 401


