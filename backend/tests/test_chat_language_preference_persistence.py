import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision
from app.models.schemas import Assignment


def test_language_preference_persists_only_when_matches_lang_hint(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="English", dueDate=None, courseName="English")],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    # Case 1: mismatch (English user message but model claims sv) => do not persist.
    async def fake_coach_decide_sv(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="Hej",
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide_sv)

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hello",  # lang_hint => en
            "current_plan": {"weekStart": "2026-01-13", "items": [{"id": "p1", "title": "Start x", "dueDate": None, "estimatedMinutes": 15, "status": "todo", "sourceAssignmentId": "a1"}]},
        },
    )
    assert r.status_code == 200

    from app.core.db import get_user_state

    state = get_user_state(user_id="u1")
    assert "language_preference" not in state

    # Case 2: match (Swedish user message with åäö and model says sv) => persist.
    async def fake_coach_decide_sv2(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="Okej",
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide_sv2)
    r2 = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hej, jag är klar.",  # lang_hint => sv
            "current_plan": {"weekStart": "2026-01-13", "items": [{"id": "p1", "title": "Start x", "dueDate": None, "estimatedMinutes": 15, "status": "todo", "sourceAssignmentId": "a1"}]},
        },
    )
    assert r2.status_code == 200
    state2 = get_user_state(user_id="u1")
    assert state2.get("language_preference") == "sv"


