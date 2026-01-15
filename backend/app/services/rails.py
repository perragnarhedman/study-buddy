from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.models.schemas import PlanItem, WeeklyPlan, new_id, week_start_iso


MAX_ITEMS = 15
MIN_MINUTES = 10
MAX_MINUTES = 20


def enforce_week_start(plan: WeeklyPlan, *, today: Optional[date] = None) -> WeeklyPlan:
    today = today or date.today()
    expected = week_start_iso(today)
    if plan.weekStart != expected:
        plan.weekStart = expected  # type: ignore[attr-defined]
    return plan


def normalize_weekly_plan(obj: Any, *, today: Optional[date] = None) -> Optional[WeeklyPlan]:
    """
    Attempt to coerce/normalize unknown JSON-ish object into a WeeklyPlan that meets rails.
    Returns None if it cannot be normalized safely.
    """
    today = today or date.today()
    expected_week_start = week_start_iso(today)

    if not isinstance(obj, dict):
        return None
    items_raw = obj.get("items")
    if not isinstance(items_raw, list):
        return None

    items: list[PlanItem] = []
    for raw in items_raw[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            continue

        mins = raw.get("estimatedMinutes")
        if not isinstance(mins, int):
            mins = MIN_MINUTES
        mins = max(MIN_MINUTES, min(MAX_MINUTES, mins))

        status = raw.get("status")
        if status not in ("todo", "doing", "done"):
            status = "todo"

        pid = raw.get("id")
        if not isinstance(pid, str) or not pid:
            pid = new_id()

        due = raw.get("dueDate")
        due = due if isinstance(due, str) else None

        src = raw.get("sourceAssignmentId")
        src = src if isinstance(src, str) else None

        items.append(
            PlanItem(
                id=pid,
                title=title.strip(),
                dueDate=due,
                estimatedMinutes=mins,
                status=status,
                sourceAssignmentId=src,
            )
        )

    plan = WeeklyPlan(weekStart=expected_week_start, items=items)
    return plan


def ensure_actionable_titles(plan: WeeklyPlan) -> WeeklyPlan:
    # Minimal enforcement: if title doesn't start with "Start ", prefix it.
    for i in plan.items:
        if not i.title.lower().startswith("start "):
            i.title = f"Start {i.title}"  # type: ignore[attr-defined]
    return plan


def rails_enforce(plan: WeeklyPlan, *, today: Optional[date] = None) -> WeeklyPlan:
    plan.items = plan.items[:MAX_ITEMS]  # type: ignore[attr-defined]
    for i in plan.items:
        mins = i.estimatedMinutes if isinstance(i.estimatedMinutes, int) else MIN_MINUTES
        i.estimatedMinutes = max(MIN_MINUTES, min(MAX_MINUTES, mins))  # type: ignore[attr-defined]
    plan = enforce_week_start(plan, today=today)
    plan = ensure_actionable_titles(plan)
    return plan


