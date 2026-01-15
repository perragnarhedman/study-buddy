from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.models.schemas import WeeklyPlan


def test_weekly_plan_schema() -> None:
    client = TestClient(app)
    r = client.get("/plan/week")
    assert r.status_code == 200
    WeeklyPlan.model_validate(r.json())


def test_chat_send_returns_best_next_action_and_mentions_it() -> None:
    # Ensure OpenAI coaching doesn't run during tests.
    import os

    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()

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
    r = client.post("/chat/send", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("best_next_action") is not None
    assert body["best_next_action"]["title"] == "Start English essay draft: 15 min"
    assert "Start English essay draft" in body["assistant_message"]["text"]


