from typing import Optional

from fastapi import APIRouter, Depends

from app.models.schemas import (
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    iso_now,
    new_id,
)
from app.core.auth import get_optional_user_id
from app.services.openai_client import coach_text
from app.services.planner import coach_message_for_action
from app.services.planning import best_next_action_from_plan, generate_weekly_plan_with_fallback

router = APIRouter()


@router.post("/chat/send", response_model=ChatSendResponse)
async def chat_send(
    payload: ChatSendRequest, user_id: Optional[str] = Depends(get_optional_user_id)
) -> ChatSendResponse:
    # Must ALWAYS return assistant_message + exactly ONE best_next_action.
    if payload.current_plan and payload.current_plan.items:
        best_next_action = best_next_action_from_plan(payload.current_plan)
    else:
        plan, _meta = await generate_weekly_plan_with_fallback(user_id=user_id)
        best_next_action = best_next_action_from_plan(plan)

    mins = best_next_action.estimatedMinutes or 15
    mins = max(10, min(20, mins))

    # OpenAI (optional) for coaching text only, with deterministic fallback.
    try:
        text = await coach_text(payload.user_message, best_next_action.title, mins)
        if best_next_action.title not in text:
            text = f"{text}\n\nNext: {best_next_action.title}."
    except Exception:
        text = coach_message_for_action(best_next_action)

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


