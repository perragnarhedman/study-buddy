import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_chat_does_not_offer_done_items_as_candidates(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    # Persist done state for sourceAssignmentId=a1.
    from app.core.db import set_assignment_status

    set_assignment_status(user_id="u1", source_assignment_id="a1", status="done", updated_at=1)

    import app.routes.chat as chat_route

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        # Ensure the done item isn't offered to the model.
        plan_items_json = kwargs.get("plan_items_json") or ""
        assert '"sourceAssignmentId": "a1"' not in plan_items_json
        return CoachDecision(assistant_text="OK", reply_language="en", intent="recommend", selected_plan_item_id="a2-1")

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "What next?",
            "current_plan": {
                "weekStart": "2026-01-19",
                "items": [
                    {
                        "id": "a1-1",
                        "title": "Reading",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    },
                    {
                        "id": "a2-1",
                        "title": "Math",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a2",
                    },
                ],
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["best_next_action"]["id"] == "a2-1"


