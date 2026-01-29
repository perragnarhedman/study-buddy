import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.models.agent import CoachDecision
from app.models.schemas import WeeklyPlan


def test_weekly_plan_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.services.planning as planning_module

    async def fake_plan_week(*args, **kwargs) -> str:
        return """
        {
          "weekStart": "2026-01-13",
          "items": [
            {
              "id": "p1",
              "title": "Start Homework 1A: 15 min",
              "dueDate": null,
              "estimatedMinutes": 15,
              "status": "todo",
              "sourceAssignmentId": "a1"
            }
          ]
        }
        """.strip()

    monkeypatch.setattr(planning_module, "plan_week", fake_plan_week)

    client = TestClient(app)
    from app.core.auth import issue_session_token

    token = issue_session_token("u1")
    r = client.get("/plan/week", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    WeeklyPlan.model_validate(r.json())


def test_chat_send_returns_best_next_action_and_mentions_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a3", title="English essay", dueDate="2026-01-20", courseName="English", description=None, url=None, estimatedMinutes=None),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="OK — let’s do English next.",
            reply_language="en",
            selected_plan_item_id="p1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    payload = {
        "user_message": "Help me get started",
        "current_plan": {
            "weekStart": "2026-01-13",
            "items": [
                {
                    "id": "p1",
                    "title": "Start English essay draft: 15 min",
                    "dueDate": "2026-01-20",
                    "estimatedMinutes": 15,
                    "status": "todo",
                    "sourceAssignmentId": "a3",
                }
            ],
        },
    }
    from app.core.auth import issue_session_token

    token = issue_session_token("u1")
    r = client.post("/chat/send", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("best_next_action") is not None
    assert body["best_next_action"]["title"] == "Start English essay draft: 15 min"
    assert body["assistant_message"]["text"]


def test_chat_send_respects_user_preference_for_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="Math homework", dueDate="2026-01-20", courseName="Math", description=None, url=None, estimatedMinutes=None),
                Assignment(id="a3", title="English essay", dueDate="2026-01-20", courseName="English", description=None, url=None, estimatedMinutes=None),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        # Model selects the English item when the user prefers it.
        return CoachDecision(
            assistant_text="Sure — let’s do English today.",
            reply_language="en",
            selected_plan_item_id="e1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    payload = {
        "user_message": "I want to do English today",
        "current_plan": {
            "weekStart": "2026-01-13",
            "items": [
                {
                    "id": "m1",
                    "title": "Start Math Homework 1A: 15 min",
                    "dueDate": "2026-01-20",
                    "estimatedMinutes": 15,
                    "status": "todo",
                    "sourceAssignmentId": "a1",
                },
                {
                    "id": "e1",
                    "title": "Start English essay draft: 15 min",
                    "dueDate": "2026-01-20",
                    "estimatedMinutes": 15,
                    "status": "todo",
                    "sourceAssignmentId": "a3",
                },
            ],
        },
    }
    from app.core.auth import issue_session_token

    token = issue_session_token("u1")
    r = client.post("/chat/send", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["best_next_action"]["title"] == "Start English essay draft: 15 min"


