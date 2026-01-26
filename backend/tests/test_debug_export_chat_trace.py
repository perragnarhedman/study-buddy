import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.main import app
from app.models.agent import CoachDecision


def test_debug_export_writes_trace_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DEBUG_EXPORT_ENABLED", "true")
    monkeypatch.setenv("DEBUG_EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()

    import app.routes.chat as chat_route

    async def fake_coach_decide_with_raw(**kwargs) -> tuple[CoachDecision, str]:
        return (
            CoachDecision(
                assistant_text="Hej!",
                reply_language="sv",
                selected_plan_item_id="p1",
            ),
            "RAW MODEL OUTPUT",
        )

    monkeypatch.setattr(chat_route, "coach_decide_with_raw", fake_coach_decide_with_raw)

    token = issue_session_token("u1")
    client = TestClient(app)
    r = client.post(
        "/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_message": "Hej",
            "current_plan": {
                "weekStart": "2026-01-13",
                "items": [
                    {
                        "id": "p1",
                        "title": "Start something",
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

    exports_dir = tmp_path / "exports"
    # date partition directory should exist (UTC date)
    date_dirs = [p for p in exports_dir.iterdir() if p.is_dir()]
    assert date_dirs, "expected YYYY-MM-DD directory"
    files = list(date_dirs[0].glob("*.json"))
    assert files, "expected at least one trace file"

    obj = json.loads(files[0].read_text(encoding="utf-8"))
    assert obj["type"] == "chat_trace"
    assert "payload" in obj
    assert obj["payload"]["user_message"] == "Hej"
    assert "attempts" in obj["payload"]
    assert obj["payload"]["attempts"][0]["prompt"]
    assert obj["payload"]["attempts"][0]["raw_model_output"] == "RAW MODEL OUTPUT"


