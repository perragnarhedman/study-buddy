import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app


def test_chat_send_returns_503_when_coach_decide_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_coach_decide(**kwargs):
        raise TimeoutError("read_timeout")

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {issue_session_token('u1')}"},
        json={
            "user_message": "Help me",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start Homework: 15 min",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    }
                ],
            },
        },
    )
    assert r.status_code == 503


