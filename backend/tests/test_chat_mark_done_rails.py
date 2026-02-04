import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision
from app.models.schemas import Assignment


def test_chat_completion_rail_infers_mark_done_when_unambiguous(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a-eng", title="English essay draft", dueDate=None, courseName="English"),
                Assignment(id="a-math", title="Math worksheet", dueDate=None, courseName="Math"),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        # Model forgets to set mark_done; server rail should infer from user text + candidates.
        return CoachDecision(
            assistant_text="Nice work — what next?",
            reply_language="en",
            selected_assignment_id=None,
            mark_done_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "I finished the English essay.",
            "current_plan": {
                "weekStart": "2026-01-19",
                "items": [
                    {"id": "a-eng-1", "title": "English essay", "dueDate": None, "estimatedMinutes": 60, "status": "todo", "sourceAssignmentId": "a-eng"},
                    {"id": "a-math-1", "title": "Math worksheet", "dueDate": None, "estimatedMinutes": 30, "status": "todo", "sourceAssignmentId": "a-math"},
                ],
            },
        },
    )
    assert r.status_code == 200

    from app.core.db import get_assignment_status_map

    m = get_assignment_status_map(user_id="u1")
    assert m.get("a-eng") == "done"


