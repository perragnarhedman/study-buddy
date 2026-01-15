from typing import Optional

from fastapi import APIRouter, Depends

from app.models.schemas import WeeklyPlan
from app.core.auth import get_optional_user_id
from app.services.planning import generate_weekly_plan_with_fallback

router = APIRouter()


@router.get("/plan/week", response_model=WeeklyPlan)
async def get_week_plan(user_id: Optional[str] = Depends(get_optional_user_id)) -> WeeklyPlan:
    # Must always succeed: fallback chain inside.
    plan, _meta = await generate_weekly_plan_with_fallback(user_id=user_id)
    return plan


