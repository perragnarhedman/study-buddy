import asyncio

import pytest

from app.core.config import get_settings
from app.services import assignment_source as assignment_source_module
from app.services import planning as planning_module


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_openai_missing_uses_deterministic_planner() -> None:
    # Ensure OpenAI disabled.
    try:
        import os

        os.environ.pop("OPENAI_API_KEY", None)
    except Exception:
        pass
    _reset_settings()

    plan, meta = asyncio.run(planning_module.generate_weekly_plan_with_fallback(user_id=None))
    assert meta["planner"] == "deterministic"
    assert plan.items
    assert plan.weekStart


def test_llm_invalid_json_falls_back_to_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _reset_settings()

    async def fake_plan_week(*args, **kwargs) -> str:
        return "not-json"

    monkeypatch.setattr(planning_module, "plan_week", fake_plan_week)

    plan, meta = asyncio.run(planning_module.generate_weekly_plan_with_fallback(user_id=None))
    assert meta["planner"] == "deterministic"
    assert plan.items


def test_llm_violates_rails_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _reset_settings()

    bad = {
        "weekStart": "1999-01-01",
        "items": [
            {
                "id": f"i{i}",
                "title": f"Task {i}",
                "dueDate": None,
                "estimatedMinutes": 60,
                "status": "todo",
                "sourceAssignmentId": None,
            }
            for i in range(30)
        ],
    }

    async def fake_plan_week(*args, **kwargs) -> str:
        import json

        return json.dumps(bad)

    monkeypatch.setattr(planning_module, "plan_week", fake_plan_week)

    plan, meta = asyncio.run(planning_module.generate_weekly_plan_with_fallback(user_id=None))
    assert meta["planner"] == "llm"
    assert len(plan.items) <= 15
    assert all(10 <= (i.estimatedMinutes or 0) <= 20 for i in plan.items)


def test_classroom_failure_uses_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_user_id: str):
        raise ConnectionError("boom")

    monkeypatch.setattr(assignment_source_module, "fetch_classroom_assignments", fake_fetch)

    assignments, meta = asyncio.run(assignment_source_module.select_assignments(user_id="u1"))
    assert assignments
    assert meta["used_fixture"] is True


def test_classroom_empty_uses_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(_user_id: str):
        return []

    monkeypatch.setattr(assignment_source_module, "fetch_classroom_assignments", fake_fetch)

    assignments, meta = asyncio.run(assignment_source_module.select_assignments(user_id="u1"))
    assert assignments
    assert meta["used_fixture"] is True


