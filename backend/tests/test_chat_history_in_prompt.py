import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_chat_includes_recent_history_in_prompt(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import append_chat_history

    append_chat_history(user_id="u1", role="user", text="Hej", created_at=1)
    append_chat_history(user_id="u1", role="assistant", text="Hej! Vad vill du jobba med?", created_at=2)

    import app.routes.chat as chat_route

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        hist = kwargs.get("conversation_history") or ""
        assert "user: Hej" in hist
        assert "assistant: Hej! Vad vill du jobba med?" in hist
        return CoachDecision(
            reply_language="sv",
            intent="continue",
            assistant_text="Bra, vi fortsätter.",
            selected_plan_item_id="p1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Okej",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start something",
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


