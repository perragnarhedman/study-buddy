import json
import time
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
from app.core.db import get_assignment_status_map, set_assignment_status
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
        try:
            plan, _meta = await generate_weekly_plan_openai_required(user_id=user_id)
            plan_items = plan.items
        except Exception as e:
            print(f"chat_send openai_plan_error={type(e).__name__}")
            raise HTTPException(status_code=503, detail="OpenAI unavailable")

    # If we have persisted status (requires auth), override current_plan statuses so we don't re-suggest done work.
    if user_id and payload.current_plan and payload.current_plan.items:
        status_map = get_assignment_status_map(user_id=user_id)
        if status_map:
            for it in plan_items:
                sid = it.sourceAssignmentId
                if sid and sid in status_map:
                    it.status = status_map[sid]

    assignments_by_id = {}
    if user_id:
        assignments, _meta = await select_assignments(user_id)
        assignments_by_id = {a.id: a for a in assignments}

    # Only offer non-done items as candidates to the coach.
    candidate_items = [it for it in plan_items if it.status != "done"][:12]
    candidates = []
    for it in candidate_items:
        desc = ""
        course_name = ""
        assignment_url = ""
        assignment_title = ""
        if it.sourceAssignmentId and it.sourceAssignmentId in assignments_by_id:
            a = assignments_by_id[it.sourceAssignmentId]
            assignment_title = a.title or ""
            course_name = a.courseName or ""
            assignment_url = a.url or ""
            d = a.description
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
                "courseName": course_name,
                "assignmentTitle": assignment_title,
                "url": assignment_url,
            }
        )

    assignment_instructions = ""

    try:
        decision = await coach_decide(
            user_message=payload.user_message,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
        )
    except Exception as e:
        # Treat OpenAI connectivity / runtime errors as 503.
        print(f"chat_send openai_error={type(e).__name__}")
        raise HTTPException(status_code=503, detail="OpenAI unavailable")

    candidate_ids = {it.id for it in candidate_items}
    if decision.selected_plan_item_id not in candidate_ids:
        raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")
    selected = next((it for it in plan_items if it.id == decision.selected_plan_item_id), None)
    if selected is None:
        raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")

    # Optional: persist done status.
    if decision.mark_done_plan_item_id:
        done_item = next((it for it in plan_items if it.id == decision.mark_done_plan_item_id), None)
        if done_item is None:
            raise HTTPException(status_code=502, detail="OpenAI returned invalid mark_done_plan_item_id")
        if user_id and done_item.sourceAssignmentId:
            set_assignment_status(
                user_id=user_id,
                source_assignment_id=done_item.sourceAssignmentId,
                status="done",
                updated_at=int(time.time()),
            )

    text = (decision.assistant_text or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI returned empty response")

    best_next_action = selected

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


