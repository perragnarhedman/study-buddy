from __future__ import annotations
from datetime import date, datetime
from typing import Iterable, Optional

from app.models.schemas import Assignment, PlanItem, WeeklyPlan, new_id, week_start_iso


DEFAULT_ESTIMATE_MINUTES = 30
MIN_MINUTES = 10
MAX_MINUTES = 180
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
        if len(items) >= cap_items:
            break
        mins_raw = a.estimatedMinutes if isinstance(a.estimatedMinutes, int) else DEFAULT_ESTIMATE_MINUTES
        mins = max(MIN_MINUTES, min(MAX_MINUTES, mins_raw))
        items.append(
            PlanItem(
                id=new_id(),
                title=_plan_item_title(a.title, mins),
                dueDate=a.dueDate,
                estimatedMinutes=mins,
                status="todo",
                sourceAssignmentId=a.id,
            )
        )

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
    # Keep the suggested starter small even if the task estimate is large.
    mins = action.estimatedMinutes or DEFAULT_ESTIMATE_MINUTES
    mins = max(10, min(20, mins))
    return f"Do this now: {action.title}. Set a {mins}-minute timer and start."

def _plan_item_title(
    assignment_title: str,
    minutes: int,
) -> str:
    # One plan item per assignment.
    return f"Start {assignment_title}: {minutes} min"


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


