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
    get_last_selected_assignment_id,
    get_last_selected_plan_item_id,
    get_user_state,
    set_assignment_status,
    set_last_selected_assignment_id,
    set_last_selected_plan_item_id,
    upsert_user_state,
)
from app.services.openai_client import build_coach_prompt, coach_decide, coach_decide_with_raw
from app.services.assignment_source import select_assignments
from app.services.debug_export import export_chat_trace

router = APIRouter()

def _update_rolling_summary(prev: str, user_text: str, assistant_text: str, *, max_chars: int = 1200) -> str:
    """
    Rolling summary used as *optional* context for the coach prompt.
    Important: do NOT persist assistant text here (it may contain mistakes/hallucinations).

    We store only user lines and also sanitize any legacy summaries that included "A:" lines.
    """
    # Keep only user lines from previous summary (migration away from legacy U/A format).
    prev_lines = [ln.strip() for ln in (prev or "").splitlines() if ln.strip().startswith("U:")]
    combined = "\n".join(prev_lines).strip()

    new_line = f"U: {user_text.strip()}"
    combined = (combined + ("\n" if combined else "") + new_line).strip()
    if len(combined) <= max_chars:
        return combined
    return combined[-max_chars:]

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
        import logging

        logging.getLogger(__name__).warning("chat_send_400 user_message_required user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="user_message required")

    # Single source of truth: the client must provide current_plan.
    if not payload.current_plan:
        import logging

        logging.getLogger(__name__).warning("chat_send_400 current_plan_missing user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="current_plan is required")
    if not payload.current_plan.items:
        import logging

        logging.getLogger(__name__).warning("chat_send_400 current_plan_items_empty user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="current_plan.items is required")
    plan_items = payload.current_plan.items

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
    # be-crg: candidates are raw Classroom assignments (no splitting).
    last_selected_plan_item_id = get_last_selected_plan_item_id(user_id=user_id)
    last_selected_assignment_id = get_last_selected_assignment_id(user_id=user_id)

    # Filter out done assignments using persisted status, when possible.
    assignment_status_map = get_assignment_status_map(user_id=user_id)

    # Prefer assignments referenced by the current plan (keeps it relevant + bounded).
    plan_assignment_ids = {it.sourceAssignmentId for it in plan_items if it.sourceAssignmentId}
    base_assignments = [
        a
        for a in assignments
        if (not plan_assignment_ids or a.id in plan_assignment_ids)
        and assignment_status_map.get(a.id) != "done"
    ]
    if not base_assignments:
        # Fallback: still provide *some* candidates if plan ids don't align.
        base_assignments = [a for a in assignments if assignment_status_map.get(a.id) != "done"]

    # Follow-up handling: if the student just acknowledges (e.g. "Ja.", "Ok"), continue the last selected thread.
    ut = user_text.strip().lower().strip(".!?")
    ack = ut in {"ja", "japp", "ok", "okej", "yes", "yep", "sure", "kör", "bra"}
    if ack and last_selected_assignment_id:
        candidate_assignments = [a for a in base_assignments if a.id == last_selected_assignment_id][:1]
        if not candidate_assignments:
            candidate_assignments = base_assignments[:12]
    else:
        candidate_assignments = base_assignments[:12]

    candidates = []
    for a in candidate_assignments:
        desc = ""
        due_soon = False
        if isinstance(a.dueDate, str) and a.dueDate:
            try:
                dt = datetime.fromisoformat(a.dueDate.replace("Z", "+00:00"))
                due_soon = (dt.date() - datetime.now(timezone.utc).date()).days <= 3
            except Exception:
                due_soon = False
        d = a.description
        if isinstance(d, str):
            desc = d.strip()[:1000]
        candidates.append(
            {
                # Candidate id is the raw assignment id.
                "id": a.id,
                "title": a.title,
                "courseName": a.courseName,
                "dueDate": a.dueDate,
                "estimatedMinutes": a.estimatedMinutes,
                "description": desc,
                "url": a.url,
                "status": assignment_status_map.get(a.id, "todo"),
                "is_last_selected": bool(last_selected_assignment_id and a.id == last_selected_assignment_id),
                "is_due_soon": due_soon,
            }
        )

    assignment_instructions = ""
    # Keep only the last 5 turns (≈10 messages) to reduce prompt size + reduce
    # amplification of any earlier mistakes in history.
    hist = get_chat_history(user_id=user_id, limit=10)
    conversation_history = "\n".join([f"{h['role']}: {h['text']}" for h in hist])
    user_state_obj = get_user_state(user_id=user_id)
    conversation_summary = str(user_state_obj.get("conversation_summary") or "")
    user_state_json = json.dumps(user_state_obj, ensure_ascii=False)

    async def _call_coach(extra_note: str = ""):
        msg = user_text if not extra_note else f"{user_text}\n\nNOTE: {extra_note}"
        if ack and (last_selected_assignment_id or last_selected_plan_item_id):
            msg = f"{msg}\n\nNOTE: The student is acknowledging your previous suggestion. Continue the same task/thread; do not switch subjects."
        prompt = build_coach_prompt(
            user_message=msg,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
            conversation_history=conversation_history,
            conversation_summary=conversation_summary,
            user_state_json=user_state_json,
        )
        attempts.append(
            {
                "extra_note": extra_note,
                "user_message_to_model": msg,
                "prompt": prompt,
            }
        )
        # Only capture raw model output when debug export is enabled. This keeps
        # the default path compatible with tests that monkeypatch coach_decide.
        from app.core.config import get_settings

        settings = get_settings()
        if settings.debug_export_enabled:
            decision, raw = await coach_decide_with_raw(
                user_message=msg,
                plan_items_json=json.dumps(candidates, ensure_ascii=False),
                assignment_instructions=assignment_instructions,
                conversation_history=conversation_history,
                conversation_summary=conversation_summary,
                user_state_json=user_state_json,
            )
            attempts[-1]["raw_model_output"] = raw
            return decision

        return await coach_decide(
            user_message=msg,
            plan_items_json=json.dumps(candidates, ensure_ascii=False),
            assignment_instructions=assignment_instructions,
            conversation_history=conversation_history,
            conversation_summary=conversation_summary,
            user_state_json=user_state_json,
        )

    # Call coach; retry once if the model fails to select a valid candidate id.
    attempts: list[dict] = []
    try:
        decision = await _call_coach()
    except (ValueError, ValidationError) as e:
        print(f"chat_send openai_error={type(e).__name__}")
        raise HTTPException(status_code=502, detail="OpenAI returned invalid JSON")
    except Exception as e:
        print(f"chat_send openai_error={type(e).__name__}")
        raise HTTPException(status_code=503, detail="OpenAI unavailable")

    candidate_ids = {a.id for a in candidate_assignments}
    best_next_action = None
    selected_assignment_id = getattr(decision, "selected_assignment_id", None)

    # Backward compatibility during rollout: allow selecting a plan item id and translate to assignment id.
    if not selected_assignment_id and decision.selected_plan_item_id:
        pi = next((it for it in plan_items if it.id == decision.selected_plan_item_id), None)
        if pi and pi.sourceAssignmentId:
            selected_assignment_id = pi.sourceAssignmentId

    if selected_assignment_id:
        if selected_assignment_id not in candidate_ids:
            try:
                decision = await _call_coach(
                    "If you set selected_assignment_id, it MUST be one of the candidate ids (or null). Do not invent ids."
                )
            except (ValueError, ValidationError) as e:
                print(f"chat_send openai_error={type(e).__name__}")
                raise HTTPException(status_code=502, detail="OpenAI returned invalid JSON")
            except Exception as e:
                print(f"chat_send openai_error={type(e).__name__}")
                raise HTTPException(status_code=503, detail="OpenAI unavailable")
            selected_assignment_id = getattr(decision, "selected_assignment_id", None) or selected_assignment_id
            if selected_assignment_id and selected_assignment_id not in candidate_ids:
                raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")

        # Map assignment selection to best_next_action plan item (keep response compatible with iOS).
        best_next_action = next(
            (it for it in plan_items if it.sourceAssignmentId == selected_assignment_id and it.status != "done"),
            None,
        )

    # Optional: persist done status.
    # Optional: persist done status.
    mark_done_assignment_id = getattr(decision, "mark_done_assignment_id", None)
    if mark_done_assignment_id:
        set_assignment_status(
            user_id=user_id,
            source_assignment_id=mark_done_assignment_id,
            status="done",
            updated_at=int(time.time()),
        )
    elif decision.mark_done_plan_item_id:
        done_item = next((it for it in plan_items if it.id == decision.mark_done_plan_item_id), None)
        if done_item and done_item.sourceAssignmentId:
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
    upsert_user_state(
        user_id=user_id,
        language_preference=decision.reply_language,
        last_intent=None,
        conversation_summary=_update_rolling_summary(
            str(user_state_obj.get("conversation_summary") or ""),
            user_text,
            text,
        ),
        updated_at=now_ts,
    )
    if best_next_action is not None:
        set_last_selected_plan_item_id(user_id=user_id, plan_item_id=best_next_action.id, updated_at=now_ts)
    if selected_assignment_id:
        set_last_selected_assignment_id(user_id=user_id, assignment_id=selected_assignment_id, updated_at=now_ts)

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    # Debug export (best-effort).
    try:
        for a in attempts:
            a["decision"] = {
                "selected_assignment_id": getattr(decision, "selected_assignment_id", None),
                "selected_plan_item_id": getattr(decision, "selected_plan_item_id", None),
                "mark_done_assignment_id": getattr(decision, "mark_done_assignment_id", None),
                "mark_done_plan_item_id": getattr(decision, "mark_done_plan_item_id", None),
                "reply_language": getattr(decision, "reply_language", None),
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


