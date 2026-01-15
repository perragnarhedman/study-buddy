from fastapi import APIRouter

from app.models.schemas import WeeklyPlan
from app.services.planner import generate_weekly_plan, stub_assignments

router = APIRouter()


@router.get("/plan/week", response_model=WeeklyPlan)
def get_week_plan() -> WeeklyPlan:
    # Deterministic plan generation (rails).
    assignments = stub_assignments()
    return generate_weekly_plan(assignments)


