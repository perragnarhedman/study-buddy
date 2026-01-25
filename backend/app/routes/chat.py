import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.models.schemas import (
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    iso_now,
    new_id,
)
from app.core.auth import get_optional_user_id
from app.core.db import (
    append_chat_history,
    get_assignment_status_map,
    get_chat_history,
    get_last_selected_plan_item_id,
    set_assignment_status,
    set_last_selected_plan_item_id,
)
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

    user_text = (payload.user_message or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="user_message required")

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

    # Detect a lightweight user language hint (sv/en) for validation.
    def _detect_lang_hint(s: str) -> str:
        import re

        s2 = s.lower()
        if any(ch in s2 for ch in "åäö"):
            return "sv"
        # Very rough: common Swedish words (normalize punctuation).
        words = re.sub(r"[^a-zåäö]+", " ", s2).split()
        if any(w in words for w in ["hej", "tack", "okej", "klar", "färdig", "borja", "börja", "engelska", "idag"]):
            return "sv"
        return "en"

    lang_hint = _detect_lang_hint(user_text)

    def _validate_evidence(decision, candidates_list: list[dict]) -> None:
        ev = getattr(decision, "evidence", None)
        if not ev:
            return
        pid = decision.selected_plan_item_id
        c = next((x for x in candidates_list if x.get("id") == pid), None)
        if not c:
            raise HTTPException(status_code=502, detail="OpenAI returned invalid evidence")
        hay = " ".join(
            [
                str(c.get("title") or ""),
                str(c.get("description") or ""),
                str(c.get("assignmentTitle") or ""),
                str(c.get("courseName") or ""),
                str(c.get("url") or ""),
            ]
        ).lower()
        if str(ev).strip().lower() not in hay:
            raise HTTPException(status_code=502, detail="OpenAI returned ungrounded evidence")

    def _validate_no_hallucinated_details(decision, candidates_list: list[dict]) -> None:
        """
        Best-effort guardrail: if assistant_text includes concrete details (page/exercise ranges or filenames),
        ensure those substrings exist in the chosen candidate's title/description/url.
        """
        import re

        pid = decision.selected_plan_item_id
        c = next((x for x in candidates_list if x.get("id") == pid), None)
        if not c:
            raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")
        hay = " ".join(
            [
                str(c.get("title") or ""),
                str(c.get("description") or ""),
                str(c.get("assignmentTitle") or ""),
                str(c.get("courseName") or ""),
                str(c.get("url") or ""),
            ]
        ).lower()
        text = (decision.assistant_text or "").lower()

        # Numeric ranges like 45-48, 4–5, page 55
        for m in re.findall(r"\b\d+\s*[-–]\s*\d+\b", text):
            if m.replace(" ", "") not in hay.replace(" ", ""):
                raise HTTPException(status_code=502, detail="OpenAI mentioned ungrounded numeric range")
        for m in re.findall(r"\bpage\s*\d+\b|\bsidan\s*\d+\b", text):
            if m.replace(" ", "") not in hay.replace(" ", ""):
                raise HTTPException(status_code=502, detail="OpenAI mentioned ungrounded page reference")

        # Filenames ending with .pdf/.doc/.docx/.ppt/.pptx
        for m in re.findall(r"\b[\w\-\s]+\.(pdf|docx?|pptx?)\b", text):
            # re.findall returns only extension in group; re-run with finditer for full match
            break
        for it in re.finditer(r"\b[\w\-\s]+\.(?:pdf|docx?|pptx?)\b", text):
            fname = it.group(0).strip()
            if fname and fname not in hay:
                raise HTTPException(status_code=502, detail="OpenAI mentioned ungrounded filename")

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

    # If the student is just acknowledging (ok/yes/etc), prefer continuing the previous selection.
    ack = user_text.lower() in {"ok", "okay", "sure", "yes", "yep", "yeah", "okej", "japp", "kör", "bra"}
    # Treat "please answer in Swedish/English" as a meta instruction, not a new task request.
    lang_request = False
    ut = user_text.lower()
    if "svenska" in ut or "på svenska" in ut or "in swedish" in ut:
        lang_request = True
    if "english" in ut or "på engelska" in ut or "in english" in ut:
        lang_request = True
    last_selected = get_last_selected_plan_item_id(user_id=user_id) if user_id else None

    base_items = [it for it in plan_items if it.status != "done"]
    if (ack or lang_request) and last_selected:
        candidate_items = [it for it in base_items if it.id == last_selected][:1]
        # If last_selected isn't in plan anymore, fall back to normal list.
        if not candidate_items:
            candidate_items = base_items[:12]
    else:
        candidate_items = base_items[:12]

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
    conversation_history = ""
    if user_id:
        hist = get_chat_history(user_id=user_id, limit=10)
        # simple text format the model can follow
        conversation_history = "\n".join([f"{h['role']}: {h['text']}" for h in hist])

    async def _call_coach(extra_note: str = ""):
        msg = user_text if not extra_note else f"{user_text}\n\nNOTE: {extra_note}"
        return await coach_decide(
            user_message=msg,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
            conversation_history=conversation_history,
        )

    # Call coach; if language mismatch, retry once with explicit correction.
    try:
        decision = await _call_coach()
        if decision.reply_language and decision.reply_language.lower() != lang_hint:
            decision = await _call_coach(f"Reply language MUST be '{lang_hint}'. Set reply_language='{lang_hint}'.")
        # Grounding validation; retry once if it fails due to evidence.
        try:
            _validate_evidence(decision, candidates)
            _validate_no_hallucinated_details(decision, candidates)
        except HTTPException:
            decision = await _call_coach(
                "Your evidence must be a short exact quote from the chosen candidate’s description/title/url. "
                "Do not invent page numbers, exercises, or file contents. "
                "If you didn't cite specifics, set evidence=null."
            )
            _validate_evidence(decision, candidates)
            _validate_no_hallucinated_details(decision, candidates)
    except HTTPException:
        # Preserve validation errors (502) rather than mapping to 503.
        raise
    except (ValueError, ValidationError) as e:
        # Most commonly: model output isn't valid JSON matching CoachDecision.
        print(f"chat_send openai_error={type(e).__name__}")
        raise HTTPException(status_code=502, detail="OpenAI returned invalid JSON")
    except Exception as e:
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
    now_ts = int(time.time())
    if user_id:
        # Update conversation memory + last selection.
        append_chat_history(user_id=user_id, role="user", text=user_text[:1200], created_at=now_ts)
        append_chat_history(user_id=user_id, role="assistant", text=text[:1200], created_at=now_ts + 1)
        set_last_selected_plan_item_id(user_id=user_id, plan_item_id=best_next_action.id, updated_at=now_ts)

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


