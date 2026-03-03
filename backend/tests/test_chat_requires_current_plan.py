import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app


def test_chat_send_succeeds_when_current_plan_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.agent import CoachDecision
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(
                    id="a1",
                    title="English essay",
                    dueDate="2026-01-20",
                    courseName="English",
                    description=None,
                    url=None,
                    estimatedMinutes=None,
                    attachments=None,
                ),
            ],
            {"source": "fake"},
        )

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="OK — let's do English next.",
            reply_language="en",
            selected_assignment_id="a1",
            mark_done_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)
    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post("/chat/send", headers={"Authorization": f"Bearer {token}"}, json={"user_message": "Hi"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("assistant_message", {}).get("text")
    assert body.get("best_next_action") is not None
    assert body["best_next_action"]["sourceAssignmentId"] == "a1"


