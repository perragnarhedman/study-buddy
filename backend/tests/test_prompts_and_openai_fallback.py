import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import prompts as prompts_module


def test_prompt_loader_reads_from_disk(tmp_path: Path) -> None:
    p = tmp_path / "coach_system.txt"
    p.write_text("SYSTEM", encoding="utf-8")
    assert prompts_module.load_text("coach_system.txt", prompts_dir=tmp_path) == "SYSTEM"


def test_chat_send_returns_503_when_openai_missing() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["SESSION_SECRET"] = "test-secret"
    get_settings.cache_clear()

    from app.core.auth import issue_session_token

    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {issue_session_token('u1')}"},
        json={
            "user_message": "Help me",
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
    assert r.status_code == 503


def test_prompts_can_format_without_missing_keys() -> None:
    from app.services.prompts import load_text, render_template

    system = render_template(
        load_text("coach_system.txt"),
        {"minutes": "15", "best_next_action_title": "Start Homework 1A: 15 min"},
    )
    user = render_template(
        load_text("coach_user.txt"),
        {
            "user_message": "Help me",
            "plan_items_json": "[]",
            "reference_assignments_json": "[]",
            "conversation_history": "",
            "conversation_summary": "",
            "user_state_json": "{}",
            "visible_chat_is_empty": "false",
        },
    )
    intro_user = render_template(
        load_text("intro_user.txt"),
        {
            "user_message": "Hi",
            "visible_chat_is_empty": "true",
        },
    )
    plan_user = render_template(
        load_text("plan_user.txt"),
        {"week_start": "2026-01-13", "assignments_json": "[]"},
    )
    # Smoke check: placeholders were replaced and JSON braces didn't break templating.
    assert "Help me" in user
    assert "Hi" in intro_user
    assert "{plan_items_json}" not in user
    assert "{visible_chat_is_empty}" not in intro_user
    assert "Decision JSON schema" in system
    assert "{week_start}" not in plan_user
    assert "{assignments_json}" not in plan_user


