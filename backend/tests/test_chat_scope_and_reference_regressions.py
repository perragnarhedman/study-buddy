import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision
from app.models.schemas import Assignment


def _auth_client() -> tuple[TestClient, str]:
    token = issue_session_token("u1")
    return TestClient(app), token


@pytest.mark.parametrize(
    "user_message",
    [
        "Kan du generera en bild åt mig?",
        "Var det Måns Zelmerlöw? Kan du kolla?",
        "Vad betyder fuck?",
    ],
)
def test_chat_adds_off_scope_note_for_non_homework_requests(
    tmp_path, monkeypatch: pytest.MonkeyPatch, user_message: str
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(
                    id="a1",
                    title="Math practice",
                    dueDate=None,
                    courseName="Math",
                    description="Uppgifter 1-10.",
                    url=None,
                    estimatedMinutes=None,
                )
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        model_message = kwargs.get("user_message") or ""
        assert "appears off-scope" in model_message
        return CoachDecision(
            assistant_text=(
                "Jag kan bara hjälpa till med uppgifter i Classroom eller uppgifter du klistrar in här.\n\n"
                "Om du vill kan du öppna uppgiften eller klistra in instruktionen så hjälper jag dig vidare."
            ),
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": user_message,
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "a1-1",
                        "title": "Start Math practice",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    assert "Classroom" in response.json()["assistant_message"]["text"]


def test_fresh_greeting_does_not_continue_hidden_old_thread(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import persist_chat_turn
    import app.routes.chat as chat_route

    persist_chat_turn(
        user_id="u1",
        user_text="Ja",
        assistant_text="Toppen - då fortsätter vi med historieuppgiften om andra världskriget.",
        now_ts=1,
        conversation_summary="U: Ja",
        language_preference="sv",
        selected_plan_item_id="a1-1",
        selected_assignment_id="a1",
        mark_done_assignment_id=None,
    )

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="History", dueDate=None, courseName="History", description="Read pages 1-10.", url=None, estimatedMinutes=None)
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        assert kwargs.get("visible_chat_is_empty") is True
        assert (kwargs.get("conversation_history") or "") == ""
        assert (kwargs.get("conversation_summary") or "") == ""
        model_message = kwargs.get("user_message") or ""
        assert "fresh greeting" in model_message
        return CoachDecision(
            assistant_text="Hej! Vad vill du ha hjälp med idag?",
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_message": "Hej", "visible_chat_is_empty": True},
    )
    assert response.status_code == 200
    assert response.json()["assistant_message"]["text"].startswith("Hej")


def test_short_followup_still_continues_when_visible_chat_not_empty(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import persist_chat_turn
    import app.routes.chat as chat_route

    persist_chat_turn(
        user_id="u1",
        user_text="Mobbning.",
        assistant_text="Vilken typ av mobbning vill du fokusera på: i skolan, på nätet, eller i en vänskapsgrupp?",
        now_ts=1,
        conversation_summary="U: Mobbning.",
        language_preference="sv",
        selected_plan_item_id=None,
        selected_assignment_id=None,
        mark_done_assignment_id=None,
    )

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="History", dueDate=None, courseName="History", description="Read pages 1-10.", url=None, estimatedMinutes=None)
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        assert kwargs.get("visible_chat_is_empty") is False
        model_message = kwargs.get("user_message") or ""
        assert "likely answering your previous question" in model_message
        return CoachDecision(
            assistant_text="Okej - då fokuserar vi på mobbning i skolan.",
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_message": "Skolan", "visible_chat_is_empty": False},
    )
    assert response.status_code == 200
    assert response.json()["assistant_message"]["text"].startswith("Okej")


def test_done_assignment_is_referenceable_without_being_recommended(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import set_assignment_status
    import app.routes.chat as chat_route

    set_assignment_status(user_id="u1", source_assignment_id="a1", status="done", updated_at=1)

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(
                    id="a1",
                    title="English essay",
                    dueDate=None,
                    courseName="English",
                    description="Write an essay with introduction, body and analysis.",
                    url="https://classroom.google.com/english",
                    estimatedMinutes=None,
                ),
                Assignment(
                    id="a2",
                    title="Math practice",
                    dueDate=None,
                    courseName="Math",
                    description="Uppgifter 1-10.",
                    url=None,
                    estimatedMinutes=None,
                ),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        active_json = kwargs.get("plan_items_json") or ""
        reference_json = kwargs.get("reference_assignments_json") or ""
        assert '"id": "a1"' not in active_json
        assert '"id": "a1"' in reference_json
        return CoachDecision(
            assistant_text=(
                "Jag kan visa den igen.\n\n"
                "Din tidigare engelskauppgift var att skriva en text med introduction, body och analysis."
            ),
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Jag hade engelska. Och jag har glömt en deluppgift. Kan du visa mig den uppgiften igen?",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "a2-1",
                        "title": "Start Math practice",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a2",
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["best_next_action"] is None
    assert "engelskauppgift" in body["assistant_message"]["text"]


def test_resolved_assignment_can_be_reopened_explicitly(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import get_assignment_status_map, set_assignment_status
    import app.routes.chat as chat_route

    set_assignment_status(user_id="u1", source_assignment_id="a1", status="done", updated_at=1)

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="English essay", dueDate=None, courseName="English", description="Old essay", url=None, estimatedMinutes=None),
                Assignment(id="a2", title="Math practice", dueDate=None, courseName="Math", description="Uppgifter 1-10.", url=None, estimatedMinutes=None),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        assert '"id": "a1"' in (kwargs.get("reference_assignments_json") or "")
        return CoachDecision(
            assistant_text="Okej - jag öppnar engelskan igen.",
            reply_language="sv",
            reopen_assignment_id="a1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_message": "Öppna engelskan igen.", "visible_chat_is_empty": True},
    )
    assert response.status_code == 200
    assert response.json()["best_next_action"]["sourceAssignmentId"] == "a1"
    assert get_assignment_status_map(user_id="u1")["a1"] == "todo"


def test_ack_after_reopen_stays_on_reopened_assignment(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import set_assignment_status
    import app.routes.chat as chat_route

    set_assignment_status(user_id="u1", source_assignment_id="a1", status="done", updated_at=1)

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="English essay", dueDate=None, courseName="English", description="Old essay", url=None, estimatedMinutes=None),
                Assignment(id="a2", title="Math practice", dueDate=None, courseName="Math", description="Uppgifter 1-10.", url=None, estimatedMinutes=None),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        user_message = kwargs.get("user_message") or ""
        if "Öppna engelskan igen." in user_message:
            return CoachDecision(
                assistant_text="Okej - jag öppnar engelskan igen.",
                reply_language="sv",
                reopen_assignment_id="a1",
            )
        assert '"id": "a1"' in (kwargs.get("plan_items_json") or "")
        assert '"id": "a2"' not in (kwargs.get("plan_items_json") or "")
        return CoachDecision(
            assistant_text="Toppen - då fortsätter vi med engelskan.",
            reply_language="sv",
            selected_assignment_id="a1",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    first = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Öppna engelskan igen.",
            "visible_chat_is_empty": True,
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {"id": "a1-1", "title": "Start English essay", "dueDate": None, "estimatedMinutes": 15, "status": "done", "sourceAssignmentId": "a1"},
                    {"id": "a2-1", "title": "Start Math practice", "dueDate": None, "estimatedMinutes": 15, "status": "todo", "sourceAssignmentId": "a2"},
                ],
            },
        },
    )
    assert first.status_code == 200
    assert first.json()["best_next_action"]["sourceAssignmentId"] == "a1"

    second = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Ja",
            "visible_chat_is_empty": False,
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {"id": "a1-1", "title": "Start English essay", "dueDate": None, "estimatedMinutes": 15, "status": "done", "sourceAssignmentId": "a1"},
                    {"id": "a2-1", "title": "Start Math practice", "dueDate": None, "estimatedMinutes": 15, "status": "todo", "sourceAssignmentId": "a2"},
                ],
            },
        },
    )
    assert second.status_code == 200
    assert second.json()["best_next_action"]["sourceAssignmentId"] == "a1"


def test_done_reference_assignment_stays_out_of_recommendations(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import set_assignment_status
    import app.routes.chat as chat_route

    set_assignment_status(user_id="u1", source_assignment_id="a1", status="done", updated_at=1)

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="English essay", dueDate=None, courseName="English", description="Old essay", url=None, estimatedMinutes=None),
                Assignment(id="a2", title="Math practice", dueDate=None, courseName="Math", description="Uppgifter 1-10.", url=None, estimatedMinutes=None),
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        assert '"id": "a1"' not in (kwargs.get("plan_items_json") or "")
        assert '"id": "a1"' in (kwargs.get("reference_assignments_json") or "")
        return CoachDecision(
            assistant_text="Börja med matten nu.",
            reply_language="sv",
            selected_assignment_id="a2",
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Vad ska jag göra nu?",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "a2-1",
                        "title": "Start Math practice",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a2",
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["best_next_action"]["sourceAssignmentId"] == "a2"


def test_short_followup_answer_adds_continue_thread_note(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import persist_chat_turn
    import app.routes.chat as chat_route

    persist_chat_turn(
        user_id="u1",
        user_text="Mobbning.",
        assistant_text="Vilken typ av mobbning vill du fokusera på: i skolan, på nätet, eller i en vänskapsgrupp?",
        now_ts=1,
        conversation_summary="U: Mobbning.",
        language_preference="sv",
        selected_plan_item_id=None,
        selected_assignment_id=None,
        mark_done_assignment_id=None,
    )

    async def fake_select_assignments(_user_id):
        return (
            [
                Assignment(id="a1", title="History", dueDate=None, courseName="History", description="Read pages 1-10.", url=None, estimatedMinutes=None)
            ],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        model_message = kwargs.get("user_message") or ""
        assert "likely answering your previous question" in model_message
        assert "Do not restart with a new greeting" in model_message
        return CoachDecision(
            assistant_text="Okej — då fokuserar vi på mobbning i skolan.",
            reply_language="sv",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client, token = _auth_client()
    response = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Skolan",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "a1-1",
                        "title": "Start History",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["assistant_message"]["text"].startswith("Okej")
