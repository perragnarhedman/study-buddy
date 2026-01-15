from datetime import timedelta, date

from fastapi import APIRouter

from app.models.schemas import PlanItem, WeeklyPlan, new_id, week_start_iso

router = APIRouter()


@router.get("/plan/week", response_model=WeeklyPlan)
def get_week_plan() -> WeeklyPlan:
    # Stubbed weekly plan for MVP scaffolding.
    week_start = date.fromisoformat(week_start_iso())
    sample_due = (week_start + timedelta(days=3)).isoformat()

    items = [
        PlanItem(
            id=new_id(),
            title="10-min starter: open your notes and list 3 key topics to review",
            dueDate=sample_due,
            estimatedMinutes=10,
            status="todo",
            sourceAssignmentId=None,
        ),
        PlanItem(
            id=new_id(),
            title="Outline: 5 bullets for your next assignment/problem set",
            dueDate=sample_due,
            estimatedMinutes=15,
            status="todo",
            sourceAssignmentId=None,
        ),
    ]
    return WeeklyPlan(weekStart=week_start.isoformat(), items=items)


