import json
import time
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.models.schemas import (
    AssignmentCard,
    ChatMessage,
    ChatSendRequest,
    ChatSendResponse,
    SetAssignmentStatusRequest,
    SetAssignmentStatusResponse,
    iso_now,
    new_id,
    week_start_iso,
)
from app.core.auth import AuthContext, require_user_id
from app.core.db import (
    append_chat_history,
    get_assignment_status_map,
    get_chat_history,
    get_last_selected_assignment_id,
    get_last_selected_plan_item_id,
    get_user_state,
    reset_conversation_state,
    set_assignment_status,
    set_last_selected_assignment_id,
    set_last_selected_plan_item_id,
    upsert_user_state,
)
from app.services.openai_client import build_coach_prompt, coach_decide, coach_decide_with_raw
from app.services.assignment_source import select_assignments
from app.services.debug_export import export_chat_trace

router = APIRouter()

def _is_overview_request(text: str) -> bool:
    """
    Detect when the user is asking for an overview/list of assignments.
    This is intentionally heuristic and deterministic (no LLM dependency).
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    # English
    if any(k in t for k in ["what do i have", "what else", "what's coming", "whats coming", "overview", "upcoming"]):
        return True
    if "assignments" in t or "homework" in t:
        return True
    if "this week" in t or "next week" in t:
        return True
    # Swedish
    if any(k in t for k in ["vad har jag", "vad mer", "översikt", "oversikt", "kommande", "uppgifter", "läxor", "laxor"]):
        return True
    if "den här veckan" in t or "denna vecka" in t or "nästa vecka" in t or "nasta vecka" in t:
        return True
    return False


def _overview_bucket(text: str) -> str:
    t = (text or "").strip().lower()
    if any(k in t for k in ["next week", "nästa vecka", "nasta vecka"]):
        return "next_week"
    if any(k in t for k in ["this week", "den här veckan", "denna vecka"]):
        return "this_week"
    return "all"


def _parse_date_loose(raw: Optional[str]) -> Optional[date]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    # 1) YYYY-MM-DD
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return date.fromisoformat(s[:10])
    except Exception:
        pass
    # 2) ISO8601 datetime
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.date()
    except Exception:
        return None


def _bucket_plan_items_for_cards(*, plan_items: list, week_start_raw: str) -> dict[str, list]:
    """
    Buckets plan items into this_week / next_week / later for card display.
    Missing/invalid due dates fall into later.
    """
    ws = _parse_date_loose(week_start_raw) or date.fromisoformat(week_start_iso())
    start_next = ws.fromordinal(ws.toordinal() + 7)
    start_after_next = ws.fromordinal(ws.toordinal() + 14)

    out = {"this_week": [], "next_week": [], "later": []}
    for it in plan_items:
        d = _parse_date_loose(getattr(it, "dueDate", None))
        if d is None:
            out["later"].append(it)
        elif d < start_next:
            out["this_week"].append(it)
        elif d < start_after_next:
            out["next_week"].append(it)
        else:
            out["later"].append(it)
    return out

def _sanitize_user_only_summary(summary: str) -> str:
    """
    Safety: legacy summaries may contain assistant lines ("A: ...") from older versions.
    For prompt robustness, keep only user lines ("U: ...").
    """
    if not isinstance(summary, str) or not summary.strip():
        return ""
    lines = [ln.strip() for ln in summary.splitlines() if ln.strip().startswith("U:")]
    return "\n".join(lines).strip()

def _is_completion_utterance(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    # English + Swedish lightweight detection.
    return any(
        k in t
        for k in [
            "i finished",
            "i've finished",
            "i have finished",
            "finished",
            "i did it",
            "done",
            "completed",
            "submitted",
            "turned in",
            "handed in",
            "klar",
            "färdig",
            "fardig",
            "lämnade in",
            "lamnade in",
            "inlämnad",
            "inlamnad",
        ]
    )

def _best_mark_done_candidate_id(*, user_text: str, candidates: list[dict]) -> Optional[str]:
    """
    Heuristic: if the user indicates completion and there is a single clear match among candidates,
    return that candidate id; otherwise None (ambiguous).
    """
    ut = (user_text or "").lower()
    if not ut:
        return None
    scored: list[tuple[int, str]] = []
    for c in candidates:
        cid = c.get("id")
        title = str(c.get("title") or "").lower()
        course = str(c.get("courseName") or "").lower()
        if not isinstance(cid, str) or not cid:
            continue
        score = 0
        if title and title in ut:
            score += 3
        if course and course in ut:
            score += 2
        # Add a small boost for title keyword overlap.
        for w in title.replace(":", " ").replace("-", " ").split():
            if len(w) >= 4 and w in ut:
                score += 1
                break
        if score > 0:
            scored.append((score, cid))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_id = scored[0]
    # Require a reasonably strong, unique match.
    if best_score < 2:
        return None
    if len(scored) >= 2 and scored[1][0] == best_score:
        return None
    return best_id

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
    # Sanitize legacy summaries before injecting into prompts (user-only lines).
    conversation_summary = _sanitize_user_only_summary(str(user_state_obj.get("conversation_summary") or ""))
    if conversation_summary:
        user_state_obj["conversation_summary"] = conversation_summary
    else:
        # Avoid leaking legacy assistant text via user_state_json.
        user_state_obj.pop("conversation_summary", None)
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

    # Safety rail: on acknowledgement, if the model returns null selection, continue last-selected thread.
    if ack and last_selected_assignment_id and not selected_assignment_id:
        if last_selected_assignment_id in candidate_ids:
            selected_assignment_id = last_selected_assignment_id
            decision.selected_assignment_id = last_selected_assignment_id

    # Safety rail: if the user indicates completion but model didn't set mark_done, auto-mark if unambiguous.
    mark_done_assignment_id = getattr(decision, "mark_done_assignment_id", None)
    if not mark_done_assignment_id and _is_completion_utterance(user_text):
        inferred = _best_mark_done_candidate_id(user_text=user_text, candidates=candidates)
        if inferred:
            mark_done_assignment_id = inferred
            decision.mark_done_assignment_id = inferred

    # Map assignment selection to best_next_action plan item (keep response compatible with iOS).
    if selected_assignment_id:
        best_next_action = next(
            (it for it in plan_items if it.sourceAssignmentId == selected_assignment_id and it.status != "done"),
            None,
        )

    # Optional: persist done status.
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
        # Persist language preference only when it matches a server-side hint.
        # This reduces stickiness from a single wrong model reply_language.
        language_preference=(
            decision.reply_language
            if isinstance(decision.reply_language, str) and decision.reply_language == lang_hint
            else None
        ),
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

    # Optional: attach assignment cards for overview-style user questions.
    assignment_cards: Optional[list[AssignmentCard]] = None
    if _is_overview_request(user_text):
        bucket = _overview_bucket(user_text)
        buckets = _bucket_plan_items_for_cards(
            plan_items=plan_items, week_start_raw=str(payload.current_plan.weekStart)
        )

        if bucket == "this_week":
            chosen = buckets["this_week"]
        elif bucket == "next_week":
            chosen = buckets["next_week"]
        else:
            chosen = buckets["this_week"] + buckets["next_week"] + buckets["later"]

        cards: list[AssignmentCard] = []
        for it in chosen:
            # Skip done items for overview cards by default.
            if getattr(it, "status", None) == "done":
                continue
            sid = getattr(it, "sourceAssignmentId", None)
            a = assignments_by_id.get(str(sid)) if isinstance(sid, str) else None

            cards.append(
                AssignmentCard(
                    id=str(sid) if isinstance(sid, str) and sid else it.id,
                    title=str(it.title),
                    courseName=(a.courseName if a else None),
                    dueDate=getattr(it, "dueDate", None),
                    estimatedMinutes=getattr(it, "estimatedMinutes", None),
                    status=getattr(it, "status", "todo"),
                    sourceAssignmentId=sid,
                    url=(a.url if a else None),
                    attachments=(a.attachments if a and a.attachments is not None else getattr(it, "attachments", None)),
                )
            )
            if len(cards) >= 10:
                break
        assignment_cards = cards

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
                    "assignment_cards_count": len(assignment_cards or []),
                },
            },
        )
    except Exception:
        pass

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
        assignment_cards=assignment_cards,
    )


@router.post("/chat/reset")
async def chat_reset(
    *,
    clear_assignment_status: bool = Query(default=False),
    clear_preferences: bool = Query(default=False),
    ctx: AuthContext = Depends(require_user_id),
) -> dict:
    """
    Reset the conversation state for the authenticated user.
    Intended for debugging and test harness workflows.
    """
    reset_conversation_state(
        user_id=ctx.user_id,
        clear_assignment_status=clear_assignment_status,
        clear_preferences=clear_preferences,
    )
    return {"status": "ok"}


@router.post("/assignment/status", response_model=SetAssignmentStatusResponse)
async def assignment_status_set(
    payload: SetAssignmentStatusRequest,
    ctx: AuthContext = Depends(require_user_id),
) -> SetAssignmentStatusResponse:
    """
    Persist assignment status updates triggered by the client UI (e.g., tapping a chat card).
    """
    set_assignment_status(
        user_id=ctx.user_id,
        source_assignment_id=payload.sourceAssignmentId,
        status=payload.status,
        updated_at=int(time.time()),
    )
    return SetAssignmentStatusResponse(status="ok")


