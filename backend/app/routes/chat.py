import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import (
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    iso_now,
    new_id,
)
from app.core.auth import get_optional_user_id
from app.services.openai_client import coach_decide
from app.services.planning import generate_weekly_plan_openai_required
from app.services.assignment_source import select_assignments

router = APIRouter()

def _require_openai() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI unavailable")


@router.post("/chat/send", response_model=ChatSendResponse)
async def chat_send(
    payload: ChatSendRequest, user_id: Optional[str] = Depends(get_optional_user_id)
) -> ChatSendResponse:
    _require_openai()

    # Candidates come from current_plan if provided; otherwise generate via OpenAI-required planner.
    if payload.current_plan and payload.current_plan.items:
        plan_items = payload.current_plan.items
    else:
        plan, _meta = await generate_weekly_plan_openai_required(user_id=user_id)
        plan_items = plan.items

    assignments_by_id = {}
    if user_id:
        assignments, _meta = await select_assignments(user_id)
        assignments_by_id = {a.id: a for a in assignments}

    candidates = []
    for it in plan_items[:12]:
        desc = ""
        if it.sourceAssignmentId and it.sourceAssignmentId in assignments_by_id:
            d = assignments_by_id[it.sourceAssignmentId].description
            if isinstance(d, str):
                desc = d[:400]
        candidates.append(
            {
                "id": it.id,
                "title": it.title,
                "dueDate": it.dueDate,
                "estimatedMinutes": it.estimatedMinutes,
                "sourceAssignmentId": it.sourceAssignmentId,
                "description": desc,
            }
        )

    assignment_instructions = candidates[0]["description"] if candidates else ""

    try:
        decision = await coach_decide(
            user_message=payload.user_message,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="OpenAI unavailable")

    selected = next((it for it in plan_items if it.id == decision.selected_plan_item_id), None)
    if selected is None:
        raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")

    text = (decision.assistant_text or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI returned empty response")

    best_next_action = selected

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


