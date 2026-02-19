from fastapi import APIRouter, Depends, HTTPException
import httpx
import logging

from app.models.schemas import WeeklyPlan
from app.core.auth import AuthContext, require_user_id
from app.services.planning import generate_weekly_plan_openai_required
from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/plan/week", response_model=WeeklyPlan)
async def get_week_plan(ctx: AuthContext = Depends(require_user_id)) -> WeeklyPlan:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI unavailable")
    try:
        plan, _meta = await generate_weekly_plan_openai_required(user_id=ctx.user_id)
        return plan
    except HTTPException:
        raise
    except (RuntimeError, ValueError, httpx.HTTPError, TimeoutError):
        # High-level only; do not log secrets.
        logger.exception("plan_week_failed openai_required=true")
        raise HTTPException(status_code=503, detail="OpenAI unavailable")


