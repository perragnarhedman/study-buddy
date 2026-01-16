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
from app.services.assignment_source import select_assignments

router = APIRouter()

_INSTRUCTION_KEYWORDS = ("instruction", "instructions", "what do i do", "what should i do", "details")


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

    assignment_description: Optional[str] = None
    if user_id and best_next_action.sourceAssignmentId:
        msg_lc = payload.user_message.lower()
        if any(k in msg_lc for k in _INSTRUCTION_KEYWORDS):
            assignments, _meta = await select_assignments(user_id)
            match = next((a for a in assignments if a.id == best_next_action.sourceAssignmentId), None)
            if match and match.description:
                assignment_description = match.description.strip()[:1200]

    # OpenAI (optional) for coaching text only, with deterministic fallback.
    try:
        user_msg = payload.user_message
        if assignment_description:
            user_msg = f"{user_msg}\n\nAssignment instructions:\n{assignment_description}"
        text = await coach_text(user_msg, best_next_action.title, mins)
        if best_next_action.title not in text:
            text = f"{text}\n\nNext: {best_next_action.title}."
    except Exception:
        if assignment_description:
            text = (
                f"Instructions:\n{assignment_description}\n\n"
                f"Next: {best_next_action.title}. Set a {mins}-minute timer and start."
            )
        else:
            text = coach_message_for_action(best_next_action)

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


