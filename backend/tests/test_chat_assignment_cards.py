import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app


def test_chat_send_overview_includes_assignment_cards(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.agent import CoachDecision
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="Essay", courseName="English", dueDate="2026-01-14"),
                Assignment(id="a2", title="Worksheet", courseName="Math", dueDate="2026-01-20"),
            ],
            {"source": "fake"},
        )

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="Here’s what you have this week.",
            reply_language="en",
            selected_assignment_id=None,
            mark_done_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)
    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "What assignments do I have this week?",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "a1-1",
                        "title": "Start Essay: 30 min",
                        "dueDate": "2026-01-14",
                        "estimatedMinutes": 30,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    },
                    {
                        "id": "a2-1",
                        "title": "Start Worksheet: 20 min",
                        "dueDate": "2026-01-20",
                        "estimatedMinutes": 20,
                        "status": "todo",
                        "sourceAssignmentId": "a2",
                    },
                ],
            },
        },
    )
    assert r.status_code == 200
    obj = r.json()
    assert "assignment_cards" in obj
    cards = obj["assignment_cards"]
    assert isinstance(cards, list)
    assert len(cards) >= 1
    # Card should carry courseName when available via sourceAssignmentId mapping.
    assert any(c.get("courseName") == "English" for c in cards)


def test_assignment_status_endpoint_persists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import get_assignment_status_map

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/assignment/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"sourceAssignmentId": "a1", "status": "done"},
    )
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
    m = get_assignment_status_map(user_id="u1")
    assert m.get("a1") == "done"


