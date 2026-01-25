from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.core.auth import issue_session_token
from app.models.agent import CoachDecision


def test_chat_instructions_includes_assignment_description(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    from app.models.schemas import Assignment

    async def fake_select_assignments(user_id):
        return (
            [
                Assignment(
                    id="a1",
                    title="Homework 1A",
                    dueDate=None,
                    courseName="Math",
                    description="Test material the students will use.",
                    url=None,
                    estimatedMinutes=None,
                )
            ],
            {"used_classroom": True, "used_fixture": False},
        )

    # Patch symbol imported in route module.
    import app.routes.chat as chat_route

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        # Ensure the assignment description flows into the candidate list.
        assert "Test material the students will use." in (kwargs.get("plan_items_json") or "")
        return CoachDecision(
            assistant_text="Here you go.",
            reply_language="en",
            intent="recommend",
            selected_plan_item_id="p1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")

    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "What are the instructions?",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start Homework 1A: 15 min",
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
    assert body["best_next_action"]["id"] == "p1"
    assert body["assistant_message"]["text"] == "Here you go."


