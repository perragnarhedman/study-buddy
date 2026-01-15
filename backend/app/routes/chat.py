from fastapi import APIRouter

from app.models.schemas import (
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    iso_now,
    new_id,
)
from app.services.planner import (
    coach_message_for_action,
    generate_weekly_plan,
    pick_best_next_action,
    stub_assignments,
)

router = APIRouter()


@router.post("/chat/send", response_model=ChatSendResponse)
def chat_send(payload: ChatSendRequest) -> ChatSendResponse:
    # Deterministic coaching: always surface exactly ONE best next action.
    plan = payload.current_plan
    if plan is None or not plan.items:
        plan = generate_weekly_plan(stub_assignments())

    best_next_action = pick_best_next_action(plan)
    assistant_text = coach_message_for_action(best_next_action)
    assistant_message = ChatMessage(
        id=new_id(),
        role="assistant",
        text=assistant_text,
        timestamp=iso_now(),
    )

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


