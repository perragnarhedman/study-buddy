from fastapi import APIRouter

from app.models.schemas import (
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    PlanItem,
    iso_now,
    new_id,
)

router = APIRouter()


@router.post("/chat/send", response_model=ChatSendResponse)
def chat_send(payload: ChatSendRequest) -> ChatSendResponse:
    # Stub response: echo intent + surface a best next action if we have a plan.
    assistant_text = (
        "Got it. I’ll keep this simple: let’s do a tiny 10–20 min starter next.\n\n"
        f"You said: {payload.user_message}"
    )
    assistant_message = ChatMessage(
        id=new_id(), role="assistant", text=assistant_text, timestamp=iso_now()
    )

    best_next_action = None
    if payload.current_plan and payload.current_plan.items:
        # Naive: first todo item.
        todo_items = [i for i in payload.current_plan.items if i.status == "todo"]
        best_next_action = todo_items[0] if todo_items else payload.current_plan.items[0]
    else:
        best_next_action = PlanItem(
            id=new_id(),
            title="10-min starter: open your task and write the first 3 bullet points",
            dueDate=None,
            estimatedMinutes=10,
            status="todo",
            sourceAssignmentId=None,
        )

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


