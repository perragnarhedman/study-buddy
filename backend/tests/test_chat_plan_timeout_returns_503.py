import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_chat_send_returns_503_when_plan_generation_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_generate_weekly_plan_openai_required(**kwargs):
        raise TimeoutError("read_timeout")

    monkeypatch.setattr(chat_route, "generate_weekly_plan_openai_required", fake_generate_weekly_plan_openai_required)

    client = TestClient(app)
    r = client.post("/chat/send", json={"user_message": "Help"})
    assert r.status_code == 503


