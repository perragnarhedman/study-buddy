import json
import time
from datetime import datetime, timezone
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
from app.core.auth import AuthContext, require_user_id
from app.core.db import (
    append_chat_history,
    get_assignment_status_map,
    get_chat_history,
    get_last_selected_plan_item_id,
    get_user_state,
    set_assignment_status,
    set_last_selected_plan_item_id,
    upsert_user_state,
)
from app.services.openai_client import build_coach_prompt, coach_decide
from app.services.planning import generate_weekly_plan_openai_required
from app.services.assignment_source import select_assignments
from app.services.debug_export import export_chat_trace

router = APIRouter()

def _require_openai() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI unavailable")


@router.post("/chat/send", response_model=ChatSendResponse)
async def chat_send(
    payload: ChatSendRequest, ctx: AuthContext = Depends(require_user_id)
) -> ChatSendResponse:
    _require_openai()
    user_id = ctx.user_id

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

    # Override current_plan statuses so we don't re-suggest done work.
    if payload.current_plan and payload.current_plan.items:
        status_map = get_assignment_status_map(user_id=user_id)
        if status_map:
            for it in plan_items:
                sid = it.sourceAssignmentId
                if sid and sid in status_map:
                    it.status = status_map[sid]

    assignments, _meta = await select_assignments(user_id)
    assignments_by_id = {a.id: a for a in assignments}

    # Candidate list for the LLM (context packaging, not the decision).
    # We keep it bounded for prompt size and filter done items.
    last_selected = get_last_selected_plan_item_id(user_id=user_id)
    base_items = [it for it in plan_items if it.status != "done"]
    candidate_items = base_items[:12]

    candidates = []
    for it in candidate_items:
        desc = ""
        course_name = ""
        assignment_url = ""
        assignment_title = ""
        due_soon = False
        if isinstance(it.dueDate, str) and it.dueDate:
            try:
                dt = datetime.fromisoformat(it.dueDate.replace("Z", "+00:00"))
                due_soon = (dt.date() - datetime.now(timezone.utc).date()).days <= 3
            except Exception:
                due_soon = False
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
                "status": it.status,
                "is_last_selected": bool(last_selected and it.id == last_selected),
                "is_due_soon": due_soon,
            }
        )

    assignment_instructions = ""
    conversation_history = ""
    hist = get_chat_history(user_id=user_id, limit=10)
    # simple text format the model can follow
    conversation_history = "\n".join([f"{h['role']}: {h['text']}" for h in hist])
    user_state_json = json.dumps(get_user_state(user_id=user_id), ensure_ascii=False)

    async def _call_coach(extra_note: str = ""):
        msg = user_text if not extra_note else f"{user_text}\n\nNOTE: {extra_note}"
        prompt = build_coach_prompt(
            user_message=msg,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
            conversation_history=conversation_history,
            user_state_json=user_state_json,
        )
        attempts.append(
            {
                "extra_note": extra_note,
                "user_message_to_model": msg,
                "prompt": prompt,
            }
        )
        return await coach_decide(
            user_message=msg,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
            conversation_history=conversation_history,
            user_state_json=user_state_json,
        )

    def _validate_intent(decision) -> None:
        intent = getattr(decision, "intent", None)
        sid = getattr(decision, "selected_plan_item_id", None)
        md = getattr(decision, "mark_done_plan_item_id", None)
        cq = getattr(decision, "clarifying_question", None)

        if intent not in ("overview", "recommend", "continue", "clarify", "mark_done"):
            raise HTTPException(status_code=502, detail="OpenAI returned invalid intent")

        if intent in ("recommend", "continue"):
            if not isinstance(sid, str) or not sid:
                raise HTTPException(status_code=502, detail="OpenAI missing selected_plan_item_id")
            if md is not None:
                raise HTTPException(status_code=502, detail="OpenAI returned unexpected mark_done_plan_item_id")
        elif intent == "mark_done":
            if not isinstance(sid, str) or not sid:
                raise HTTPException(status_code=502, detail="OpenAI missing selected_plan_item_id")
            if not isinstance(md, str) or not md:
                raise HTTPException(status_code=502, detail="OpenAI missing mark_done_plan_item_id")
        elif intent == "clarify":
            if not isinstance(cq, str) or not cq.strip():
                raise HTTPException(status_code=502, detail="OpenAI missing clarifying_question")
            if sid is not None or md is not None:
                raise HTTPException(status_code=502, detail="OpenAI returned unexpected ids for clarify")
        elif intent == "overview":
            if sid is not None or md is not None:
                raise HTTPException(status_code=502, detail="OpenAI returned unexpected ids for overview")

    # Call coach; if language mismatch, retry once with explicit correction.
    try:
        attempts: list[dict] = []
        decision = await _call_coach()
        _validate_intent(decision)
        if decision.reply_language.lower() != lang_hint:
            decision = await _call_coach(f"Reply language MUST be '{lang_hint}'. Set reply_language='{lang_hint}'.")
        # Intent + grounding validation; retry once if it fails.
        try:
            _validate_intent(decision)
            _validate_evidence(decision, candidates)
            _validate_no_hallucinated_details(decision, candidates)
        except HTTPException:
            decision = await _call_coach(
                "Your evidence must be a short exact quote from the chosen candidate’s description/title/url. "
                "Do not invent page numbers, exercises, or file contents. "
                "If you didn't cite specifics, set evidence=null."
            )
            _validate_intent(decision)
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

    intent = decision.intent
    best_next_action = None
    selected = None

    if intent in ("recommend", "continue", "mark_done"):
        candidate_ids = {it.id for it in candidate_items}
        if decision.selected_plan_item_id not in candidate_ids:
            raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")
        selected = next((it for it in plan_items if it.id == decision.selected_plan_item_id), None)
        if selected is None:
            raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")
        best_next_action = selected

    # Optional: persist done status.
    if intent == "mark_done":
        done_item = next((it for it in plan_items if it.id == decision.mark_done_plan_item_id), None)
        if done_item is None:
            raise HTTPException(status_code=502, detail="OpenAI returned invalid mark_done_plan_item_id")
        if done_item.sourceAssignmentId:
            set_assignment_status(
                user_id=user_id,
                source_assignment_id=done_item.sourceAssignmentId,
                status="done",
                updated_at=int(time.time()),
            )

    text = (decision.assistant_text or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI returned empty response")

    now_ts = int(time.time())
    # Update conversation memory + user state.
    append_chat_history(user_id=user_id, role="user", text=user_text[:1200], created_at=now_ts)
    append_chat_history(user_id=user_id, role="assistant", text=text[:1200], created_at=now_ts + 1)
    upsert_user_state(user_id=user_id, language_preference=decision.reply_language, last_intent=intent, updated_at=now_ts)
    if best_next_action is not None:
        set_last_selected_plan_item_id(user_id=user_id, plan_item_id=best_next_action.id, updated_at=now_ts)

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    # Debug export (best-effort).
    try:
        for a in attempts:
            a["decision"] = {
                "intent": getattr(decision, "intent", None),
                "selected_plan_item_id": getattr(decision, "selected_plan_item_id", None),
                "mark_done_plan_item_id": getattr(decision, "mark_done_plan_item_id", None),
                "reply_language": getattr(decision, "reply_language", None),
                "evidence": getattr(decision, "evidence", None),
                "clarifying_question": getattr(decision, "clarifying_question", None),
            }
        export_chat_trace(
            user_id=user_id,
            payload={
                "user_message": user_text,
                "lang_hint": lang_hint,
                "conversation_history": conversation_history,
                "user_state_json": user_state_json,
                "candidates": candidates,
                "attempts": attempts,
                "response": {
                    "assistant_text": text,
                    "best_next_action_id": best_next_action.id if best_next_action else None,
                },
            },
        )
    except Exception:
        pass

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


