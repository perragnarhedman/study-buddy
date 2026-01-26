import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_chat_greeting_can_return_no_selected_plan_item(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="Hej! Vad vill du jobba med idag?",
            reply_language="sv",
            selected_plan_item_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hej!",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start English essay",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    }
                ],
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("best_next_action") is None
    assert "Hej" in body["assistant_message"]["text"]


