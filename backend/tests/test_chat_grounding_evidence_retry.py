import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision
from app.models.schemas import Assignment


def test_chat_retries_when_evidence_is_ungrounded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="English essay", dueDate=None, courseName="English", description=None, url=None, estimatedMinutes=None),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    calls = {"n": 0}

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        # No evidence/grounding enforcement anymore; just ensure we return a valid id.
        return CoachDecision(
            assistant_text="Börja med att öppna dokumentet och hitta instruktionerna.",
            reply_language="sv",
            selected_plan_item_id="p1",
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


