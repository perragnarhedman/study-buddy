import json

from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.services.chat_streaming import BubbleStreamFormatter


def test_chat_send_stream_emits_progressive_bubbles(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="Homework 1A", dueDate=None, courseName="Math")],
            {"used_classroom": False, "used_fixture": False},
        )

    raw = json.dumps(
        {
            "assistant_text": "Hi! Här är en tydlig överblick.\n\nMatte först.",
            "selected_assignment_id": "a1",
            "mark_done_assignment_id": None,
            "selected_plan_item_id": None,
            "mark_done_plan_item_id": None,
            "reply_language": "sv",
        },
        ensure_ascii=False,
    )

    async def fake_stream_events(**kwargs):
        for idx in range(0, len(raw), 12):
            yield {"type": "response.output_text.delta", "delta": raw[idx : idx + 12]}

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)
    monkeypatch.setattr(chat_route, "coach_stream_raw_events", fake_stream_events)

    client = TestClient(app)
    token = issue_session_token("u1")

    with client.stream(
        "POST",
        "/chat/send_stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hej",
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
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert events[0]["type"] == "typing_started"
    assert events[-1]["type"] == "turn_completed"
    assert any(event["type"] == "best_next_action" for event in events)

    messages_by_id: dict[str, str] = {}
    completion_order: list[str] = []
    for event in events:
        if event["type"] == "message_started":
            messages_by_id[event["message_id"]] = ""
        elif event["type"] == "message_delta":
            messages_by_id[event["message_id"]] += event["delta"]
        elif event["type"] == "message_completed":
            completion_order.append(event["message_id"])

    completed_messages = [messages_by_id[mid] for mid in completion_order]
    assert completed_messages[:2] == ["Hi!", "Här är en tydlig överblick."]
    assert completed_messages[-1] == "Matte först."


def test_chat_send_stream_emits_error_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="Homework 1A", dueDate=None, courseName="Math")],
            {"used_classroom": False, "used_fixture": False},
        )

    async def fake_stream_events(**kwargs):
        raise RuntimeError("boom")
        yield

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)
    monkeypatch.setattr(chat_route, "coach_stream_raw_events", fake_stream_events)

    client = TestClient(app)
    token = issue_session_token("u1")

    with client.stream(
        "POST",
        "/chat/send_stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hej",
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
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert events[0]["type"] == "typing_started"
    assert events[-1] == {"type": "error", "message": "OpenAI unavailable"}


def test_bubble_stream_formatter_splits_subject_blocks_and_crlf() -> None:
    formatter = BubbleStreamFormatter()

    chunks = [
        "Hej!\r\n\r\nHär är det du har kvar just nu:\r\n\r\n",
        "• Math: Worksheet 5\r\n• History: WW2 reading\r\n",
        "• English: Essay draft\r\n\r\nVill du att jag hjälper dig välja?",
    ]

    events: list[dict] = []
    for chunk in chunks:
        events.extend(formatter.feed(chunk))
    events.extend(formatter.finish())

    messages_by_id: dict[str, str] = {}
    completion_order: list[str] = []
    for event in events:
        if event["type"] == "message_started":
            messages_by_id[event["message_id"]] = ""
        elif event["type"] == "message_delta":
            messages_by_id[event["message_id"]] += event["delta"]
        elif event["type"] == "message_completed":
            completion_order.append(event["message_id"])

    completed_messages = [messages_by_id[mid] for mid in completion_order]
    assert completed_messages == [
        "Hej!",
        "Här är det du har kvar just nu:",
        "• Math: Worksheet 5",
        "• History: WW2 reading",
        "• English: Essay draft",
        "Vill du att jag hjälper dig välja?",
    ]


def test_chat_send_stream_infers_named_assignment_when_model_leaves_selection_null(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route
    from app.models.schemas import Assignment

    async def fake_select_assignments(_user_id):
        return (
            [Assignment(id="a1", title="Essay", dueDate=None, courseName="English")],
            {"used_classroom": False, "used_fixture": False},
        )

    raw = json.dumps(
        {
            "assistant_text": "Okay.\n\nLet’s start with the English essay.\n\nWrite the topic and one main point.",
            "selected_assignment_id": None,
            "mark_done_assignment_id": None,
            "selected_plan_item_id": None,
            "mark_done_plan_item_id": None,
            "reply_language": "en",
        },
        ensure_ascii=False,
    )

    async def fake_stream_events(**kwargs):
        for idx in range(0, len(raw), 14):
            yield {"type": "response.output_text.delta", "delta": raw[idx : idx + 14]}

    monkeypatch.setattr(chat_route, "select_assignments", fake_select_assignments)
    monkeypatch.setattr(chat_route, "coach_stream_raw_events", fake_stream_events)

    client = TestClient(app)
    token = issue_session_token("u1")

    with client.stream(
        "POST",
        "/chat/send_stream",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Help me start the English essay.",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start Essay: 15 min",
                        "dueDate": None,
                        "estimatedMinutes": 15,
                        "status": "todo",
                        "sourceAssignmentId": "a1",
                    }
                ],
            },
        },
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    best_next_action = next(event for event in events if event["type"] == "best_next_action")
    assert best_next_action["best_next_action"]["sourceAssignmentId"] == "a1"
