from __future__ import annotations

import json
from datetime import date
from typing import Optional, Tuple

from app.core.config import get_settings
from app.models.schemas import PlanItem, WeeklyPlan, week_start_iso
from app.services.assignment_source import select_assignments
from app.services.openai_client import plan_week, _parse_json_object_relaxed
from app.services.planner import pick_best_next_action
from app.services.rails import normalize_weekly_plan, rails_enforce


async def generate_weekly_plan_openai_required(
    *, user_id: Optional[str], today: Optional[date] = None
) -> Tuple[WeeklyPlan, dict]:
    today = today or date.today()
    assignments, src_meta = await select_assignments(user_id)

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    raw = await plan_week(_assignments_json(assignments), week_start_iso(today))
    obj = _parse_json_object_relaxed(raw)
    plan = normalize_weekly_plan(obj, today=today)
    if plan is None:
        raise ValueError("normalize_failed")
    plan = rails_enforce(plan, today=today)
    print("planner=llm required=true")
    return plan, {"planner": "llm", **src_meta}


def best_next_action_from_plan(plan: WeeklyPlan) -> PlanItem:
    return pick_best_next_action(plan)


def _assignments_json(assignments) -> str:
    # Avoid logging or including huge descriptions in the prompt.
    safe = []
    for a in assignments:
        safe.append(
            {
                "id": a.id,
                "title": a.title,
                "dueDate": a.dueDate,
                "courseName": a.courseName,
                "estimatedMinutes": a.estimatedMinutes,
            }
        )
    return json.dumps(safe, ensure_ascii=False)


