import asyncio
import time
from types import SimpleNamespace

import pytest

from app.models.schemas import Assignment
from app.services import assignment_source as assignment_source_module
from app.services import classroom as classroom_module


def test_fetch_classroom_assignments_is_bounded_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        classroom_module,
        "get_settings",
        lambda: SimpleNamespace(classroom_max_concurrency=3),
    )
    monkeypatch.setattr(
        classroom_module,
        "get_tokens",
        lambda _user_id: {"access_token": "token", "refresh_token": "refresh", "expires_at": None},
    )

    async def fake_courses(_client, _token):
        return [{"id": f"c{i}", "name": f"Course {i}"} for i in range(6)]

    async def fake_coursework(_client, _token, course_id):
        await asyncio.sleep(0.05)
        return [{"id": f"w-{course_id}", "title": f"Task {course_id}"}]

    monkeypatch.setattr(classroom_module, "_list_courses", fake_courses)
    monkeypatch.setattr(classroom_module, "_list_coursework", fake_coursework)

    started = time.perf_counter()
    out = asyncio.run(classroom_module.fetch_classroom_assignments("u1"))
    elapsed = time.perf_counter() - started

    assert len(out) == 6
    # Serial time would be about 0.30s. With max concurrency=3 we expect around 0.10s.
    assert elapsed < 0.2


def test_fetch_classroom_assignments_partial_course_failures_do_not_fail_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        classroom_module,
        "get_settings",
        lambda: SimpleNamespace(classroom_max_concurrency=4),
    )
    monkeypatch.setattr(
        classroom_module,
        "get_tokens",
        lambda _user_id: {"access_token": "token", "refresh_token": "refresh", "expires_at": None},
    )

    async def fake_courses(_client, _token):
        return [{"id": "c1", "name": "One"}, {"id": "c2", "name": "Two"}, {"id": "c3", "name": "Three"}]

    async def fake_coursework(_client, _token, course_id):
        if course_id == "c2":
            raise ConnectionError("course failure")
        return [{"id": f"w-{course_id}", "title": f"Task {course_id}"}]

    monkeypatch.setattr(classroom_module, "_list_courses", fake_courses)
    monkeypatch.setattr(classroom_module, "_list_coursework", fake_coursework)

    out = asyncio.run(classroom_module.fetch_classroom_assignments("u1"))
    assert [a.id for a in out] == ["w-c1", "w-c3"]


def test_select_assignments_uses_short_ttl_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    async def fake_fetch(_user_id: str) -> list[Assignment]:
        calls["count"] += 1
        return [
            Assignment(
                id="a1",
                title="Task",
                dueDate=None,
                courseName="Math",
                description=None,
                url=None,
                estimatedMinutes=30,
            )
        ]

    monkeypatch.setattr(assignment_source_module, "fetch_classroom_assignments", fake_fetch)
    monkeypatch.setattr(
        assignment_source_module,
        "get_settings",
        lambda: SimpleNamespace(classroom_cache_ttl_seconds=30),
    )

    first, first_meta = asyncio.run(assignment_source_module.select_assignments("u-cache"))
    second, second_meta = asyncio.run(assignment_source_module.select_assignments("u-cache"))

    assert calls["count"] == 1
    assert first and second
    assert first_meta["used_classroom"] is True
    assert second_meta["used_classroom"] is True

