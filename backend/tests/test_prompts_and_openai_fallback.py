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


def test_chat_send_fallback_when_openai_missing_includes_action_and_timer() -> None:
    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()

    client = TestClient(app)
    r = client.post(
        "/chat/send",
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
    assert r.status_code == 200
    body = r.json()
    assert body["best_next_action"]["title"] == "Start Homework 1A: 15 min"
    txt = body["assistant_message"]["text"]
    assert "Start Homework 1A: 15 min" in txt
    assert "Set a 15-minute timer" in txt


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
            "tasks_context": "",
            "plan_context": "",
            "constraints_context": "",
            "best_next_action_title": "Start Homework 1A: 15 min",
            "minutes": "15",
        },
    )
    assert "Start Homework 1A: 15 min" in system + user


