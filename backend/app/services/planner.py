from __future__ import annotations
from datetime import date

from app.models.schemas import Assignment


def stub_assignments() -> list[Assignment]:
    # Deterministic local fallback if classroom+fixture sources are unavailable.
    return [
        Assignment(
            id="a1",
            title="Math problem set 3",
            dueDate=_days_from_today_iso(2),
            courseName="Math",
            description=None,
            url=None,
            estimatedMinutes=60,
        ),
        Assignment(
            id="a2",
            title="History reading: Chapter 7 notes",
            dueDate=_days_from_today_iso(4),
            courseName="History",
            description=None,
            url=None,
            estimatedMinutes=30,
        ),
        Assignment(
            id="a3",
            title="English essay draft",
            dueDate=_days_from_today_iso(6),
            courseName="English",
            description=None,
            url=None,
            estimatedMinutes=90,
        ),
    ]

def _days_from_today_iso(days: int) -> str:
    return (date.today()).fromordinal(date.today().toordinal() + days).isoformat()


