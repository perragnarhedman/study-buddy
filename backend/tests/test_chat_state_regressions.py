import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_get_chat_history_uses_most_recent_window(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Regression: get_chat_history(limit=N) must include the most recent turns, not the oldest.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import append_chat_history

    # Insert 30 messages; we expect the prompt to include only the most recent window.
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        append_chat_history(user_id="u1", role=role, text=f"m{i}", created_at=i + 1)

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="Start something", dueDate=None, courseName="Course")],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        hist = kwargs.get("conversation_history") or ""
        # Should include the most recent messages...
        assert "m29" in hist
        assert "m28" in hist
        # ...and exclude the oldest.
        assert "m0" not in hist
        assert "m1" not in hist
        return CoachDecision(
            assistant_text="OK",
            reply_language="en",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hello",
            "current_plan": {"weekStart": "2026-01-13", "items": [{"id": "p1", "title": "Start x", "dueDate": None, "estimatedMinutes": 15, "status": "todo", "sourceAssignmentId": "a1"}]},
        },
    )
    assert r.status_code == 200


def test_conversation_summary_does_not_persist_assistant_text(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Regression: conversation_summary should NOT store assistant text (it may contain hallucinations).
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="English essay", dueDate=None, courseName="English")],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    hallucinated = "You finished math already!"

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        return CoachDecision(
            assistant_text=hallucinated,
            reply_language="en",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "English.",
            "current_plan": {"weekStart": "2026-01-13", "items": [{"id": "p1", "title": "Start English", "dueDate": None, "estimatedMinutes": 15, "status": "todo", "sourceAssignmentId": "a1"}]},
        },
    )
    assert r.status_code == 200

    from app.core.db import get_user_state

    state = get_user_state(user_id="u1")
    summary = str(state.get("conversation_summary") or "")
    assert "U: English." in summary
    assert hallucinated not in summary
    assert "A:" not in summary


def test_conversation_summary_is_sanitized_on_read_before_prompt(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Regression: legacy conversation_summary may contain assistant lines ("A: ...").
    We must sanitize on read so the coach never sees assistant lines via conversation_summary or user_state_json.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    from app.core.db import upsert_user_state

    upsert_user_state(
        user_id="u1",
        conversation_summary="U: I want math\nA: You finished math already!\nU: Actually english",
        updated_at=1,
    )

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="Math worksheet", dueDate=None, courseName="Math")],
            {"used_classroom": False, "used_fixture": False},
        )

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)

    async def fake_coach_decide(**kwargs) -> CoachDecision:
        cs = str(kwargs.get("conversation_summary") or "")
        us = str(kwargs.get("user_state_json") or "")
        assert "A:" not in cs
        assert "A:" not in us
        assert "U: I want math" in cs
        return CoachDecision(
            assistant_text="OK",
            reply_language="en",
            selected_assignment_id=None,
        )

    monkeypatch.setattr(chat_route, "coach_decide", fake_coach_decide)

    client = TestClient(app)
    token = issue_session_token("u1")
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hello",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start x",
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


