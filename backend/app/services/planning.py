from __future__ import annotations

import json
from datetime import date
from typing import Optional, Tuple

from app.core.config import get_settings
from app.core.db import get_assignment_status_map
from app.models.schemas import PlanItem, WeeklyPlan, week_start_iso
from app.services.assignment_source import select_assignments
from app.services.openai_client import plan_week, _parse_json_object_relaxed
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

    # Apply persisted done/doing status (per sourceAssignmentId) if available.
    if user_id:
        status_map = get_assignment_status_map(user_id=user_id)
        if status_map:
            for it in plan.items:
                sid = it.sourceAssignmentId
                if sid and sid in status_map:
                    it.status = status_map[sid]  # "todo|doing|done"
    print("planner=llm required=true")
    return plan, {"planner": "llm", **src_meta}

def _assignments_json(assignments) -> str:
    # Keep enough context for the model to chunk work, but cap prompt size.
    safe = []
    for a in assignments:
        desc = a.description if isinstance(getattr(a, "description", None), str) else None
        if desc:
            desc = desc.strip()
            desc = desc[:1500]
        safe.append(
            {
                "id": a.id,
                "title": a.title,
                "dueDate": a.dueDate,
                "courseName": a.courseName,
                "description": desc,
                "url": a.url,
                "estimatedMinutes": a.estimatedMinutes,
            }
        )
    return json.dumps(safe, ensure_ascii=False)


