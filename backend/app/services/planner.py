from __future__ import annotations

from datetime import date, datetime
from math import ceil
from typing import Iterable, Optional

from app.models.schemas import Assignment, PlanItem, WeeklyPlan, new_id, week_start_iso


DEFAULT_CHUNK_MINUTES = 15
MIN_CHUNK_MINUTES = 10
MAX_CHUNK_MINUTES = 20
MAX_PLAN_ITEMS = 15


def stub_assignments() -> list[Assignment]:
    # Until Classroom integration exists, keep this deterministic and local.
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


def generate_weekly_plan(
    assignments: Iterable[Assignment],
    *,
    today: Optional[date] = None,
    cap_items: int = MAX_PLAN_ITEMS,
) -> WeeklyPlan:
    today = today or date.today()
    week_start = date.fromisoformat(week_start_iso(today))

    sorted_assignments = sorted(
        list(assignments),
        key=lambda a: (_due_date_sort_key(a.dueDate), a.title.lower()),
    )

    items: list[PlanItem] = []
    for a in sorted_assignments:
        parts = _split_minutes(a.estimatedMinutes)
        total_parts = len(parts)
        for part_idx, mins in enumerate(parts, start=1):
            if len(items) >= cap_items:
                break

            title = _plan_item_title(
                a.title, mins, part_idx=part_idx, total_parts=total_parts
            )
            items.append(
                PlanItem(
                    id=new_id(),
                    title=title,
                    dueDate=a.dueDate,
                    estimatedMinutes=mins,
                    status="todo",
                    sourceAssignmentId=a.id,
                )
            )
        if len(items) >= cap_items:
            break

    return WeeklyPlan(weekStart=week_start.isoformat(), items=items)


def pick_best_next_action(plan: WeeklyPlan) -> PlanItem:
    # Exactly one action: prefer todo, then whatever is first.
    todo = next((i for i in plan.items if i.status == "todo"), None)
    if todo is not None:
        return todo
    if plan.items:
        return plan.items[0]
    # Shouldn't happen for our use, but keep deterministic.
    return PlanItem(
        id=new_id(),
        title="Start your next assignment: 15 min",
        dueDate=None,
        estimatedMinutes=15,
        status="todo",
        sourceAssignmentId=None,
    )


def coach_message_for_action(action: PlanItem) -> str:
    # Must include a 10–20 minute starter suggestion derived from best_next_action.
    mins = action.estimatedMinutes or DEFAULT_CHUNK_MINUTES
    mins = max(MIN_CHUNK_MINUTES, min(MAX_CHUNK_MINUTES, mins))
    return f"Do this now: {action.title}. Set a {mins}-minute timer and start."


def _split_minutes(total: Optional[int]) -> list[int]:
    if total is None:
        return [DEFAULT_CHUNK_MINUTES]
    if total <= MAX_CHUNK_MINUTES:
        return [max(MIN_CHUNK_MINUTES, total)]

    # Choose number of chunks ~15 min each, then distribute to keep each 10–20 min.
    n = ceil(total / DEFAULT_CHUNK_MINUTES)
    base = total // n
    rem = total % n
    chunks = [base + (1 if i < rem else 0) for i in range(n)]

    # Safety clamp (should already be within 10–20 for typical inputs).
    out: list[int] = []
    for c in chunks:
        out.append(max(MIN_CHUNK_MINUTES, min(MAX_CHUNK_MINUTES, c)))
    return out


def _plan_item_title(
    assignment_title: str, minutes: int, *, part_idx: int, total_parts: int
) -> str:
    # Keep actionable and consistent: “Start <assignment>: 15 min”
    # If split into multiple chunks, add (1/4) etc for clarity in UI.
    suffix = f" ({part_idx}/{total_parts})" if total_parts > 1 else ""
    return f"Start {assignment_title}{suffix}: {minutes} min"


def _due_date_sort_key(due_iso: Optional[str]) -> tuple[int, str]:
    # Missing due date is lowest priority (last).
    if not due_iso:
        return (1, "9999-12-31")
    # Accept ISO8601 datetime or date.
    try:
        if "T" in due_iso:
            parsed = datetime.fromisoformat(due_iso.replace("Z", "+00:00")).date()
        else:
            parsed = date.fromisoformat(due_iso)
        return (0, parsed.isoformat())
    except Exception:
        # If malformed, treat as missing (lowest priority).
        return (1, "9999-12-31")


def _days_from_today_iso(days: int) -> str:
    return (date.today()).fromordinal(date.today().toordinal() + days).isoformat()


