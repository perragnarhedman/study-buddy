import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_chat_retries_when_evidence_is_ungrounded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    calls = {"n": 0}

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        calls["n"] += 1
        if calls["n"] == 1:
            # Ungrounded evidence -> should trigger retry
            return CoachDecision(
                assistant_text="Läs sidor 45–48 och gör 4–5.",
                selected_plan_item_id="p1",
                reply_language="sv",
                evidence="pages 45-48",
            )
        # Retry must include the evidence correction note.
        assert "evidence must be a short exact quote" in (kwargs.get("user_message") or "")
        return CoachDecision(
            assistant_text="Börja med att öppna PDF:en och skumma första sidan.",
            selected_plan_item_id="p1",
            reply_language="sv",
            evidence="skim the PDF",
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
                        "title": "Start English essay: skim the PDF",
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
    assert calls["n"] == 2


