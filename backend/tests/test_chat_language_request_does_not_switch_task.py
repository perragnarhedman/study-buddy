import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_chat_language_request_reuses_last_selected_candidate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import set_last_selected_plan_item_id

    set_last_selected_plan_item_id(user_id="u1", plan_item_id="eng-1", updated_at=1)

    import app.routes.chat as chat_route

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        pj = kwargs.get("plan_items_json") or ""
        # Candidate list includes both; last-selected is flagged and included in user_state_json.
        assert '"id": "eng-1"' in pj
        assert '"id": "math-1"' in pj
        assert '"is_last_selected": true' in pj
        assert '"last_selected_plan_item_id": "eng-1"' in (kwargs.get("user_state_json") or "")
        return CoachDecision(
            reply_language="sv",
            intent="continue",
            assistant_text="Självklart — jag kan svara på svenska.",
            selected_plan_item_id="eng-1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Kan du svara på svenska?",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "eng-1",
                        "title": "Start English essay",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    },
                    {
                        "id": "math-1",
                        "title": "Start Algebra",
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
    assert r.json()["best_next_action"]["id"] == "eng-1"


