import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision
from app.models.schemas import Assignment


def test_chat_can_mark_done_and_plan_reflects_it(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    # Patch assignments selection used by /plan/week.
    import app.services.planning as planning_module

    async def fake_select_assignments(user_id):
        return (
            [
                Assignment(
                    id="a1",
                    title="English reading",
                    dueDate=None,
                    courseName="English",
                    description="Read pages 34-64.\n\nAttachments:\n- PDF: https://drive.example/file\n",
                    url="https://drive.example/file",
                    estimatedMinutes=None,
                ),
                Assignment(
                    id="a2",
                    title="Math practice",
                    dueDate=None,
                    courseName="Math",
                    description=None,
                    url=None,
                    estimatedMinutes=None,
                ),
            ],
            {"used_classroom": True, "used_fixture": False},
        )

    monkeypatch.setattr(planning_module, "select_assignments", fake_select_assignments)

    # Patch OpenAI planner call to be deterministic in tests.
    async def fake_plan_week(*args, **kwargs) -> str:
        return """
        {
          "weekStart": "2026-01-19",
          "items": [
            {
              "id": "a1-1",
              "title": "Read pages 34-42",
              "dueDate": null,
              "estimatedMinutes": 15,
              "status": "todo",
              "sourceAssignmentId": "a1"
            },
            {
              "id": "a2-1",
              "title": "Start math set: first 3 problems",
              "dueDate": null,
              "estimatedMinutes": 15,
              "status": "todo",
              "sourceAssignmentId": "a2"
            }
          ]
        }
        """.strip()

    monkeypatch.setattr(planning_module, "plan_week", fake_plan_week)

    # Patch coach decision: mark a1 as done, recommend a2 next.
    import app.routes.chat as chat_route

    async def fake_select_assignments(user_id):
        return (
            [
                Assignment(
                    id="a1",
                    title="English reading",
                    dueDate=None,
                    courseName="English",
                    description="Read pages 34-64.\n\nAttachments:\n- PDF: https://drive.example/file\n",
                    url="https://drive.example/file",
                    estimatedMinutes=None,
                ),
                Assignment(
                    id="a2",
                    title="Math practice",
                    dueDate=None,
                    courseName="Math",
                    description=None,
                    url=None,
                    estimatedMinutes=None,
                ),
            ],
            {"used_classroom": True, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text="Got it — marked that as done. Next, try the first 3 math problems.",
            reply_language="en",
            selected_plan_item_id="a2-1",
            mark_done_plan_item_id="a1-1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    token = issue_session_token("u1")
    client = TestClient(app)

    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "I'm done with the reading",
            "current_plan": {
                "weekStart": "2026-01-19",
                "items": [
                    {
                        "id": "a1-1",
                        "title": "Read pages 34-42",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    },
                    {
                        "id": "a2-1",
                        "title": "Start math set: first 3 problems",
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

    # Plan endpoint should now reflect persisted done state for a1.
    r2 = client.get("/plan/week", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    body = r2.json()
    a1_item = next(i for i in body["items"] if i["sourceAssignmentId"] == "a1")
    assert a1_item["status"] == "done"


