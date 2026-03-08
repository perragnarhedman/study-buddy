from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.core.auth import AuthContext, require_user_id
from app.core.db import (
    get_assignment_status_map,
    get_chat_history,
    get_last_selected_assignment_id,
    get_last_selected_plan_item_id,
    get_user_state,
    persist_chat_turn,
    reset_conversation_state,
)
from app.core.logging import get_request_id
from app.models.agent import CoachDecision
from app.models.schemas import ChatMessage, ChatSendRequest, ChatSendResponse, PlanItem, iso_now, new_id
from app.services.assignment_source import select_assignments
from app.services.chat_streaming import AssistantTextJSONStreamParser, BubbleStreamFormatter
from app.services.debug_export import export_chat_trace
from app.services.openai_client import (
    _parse_json_object_relaxed,
    build_coach_prompt,
    coach_decide,
    coach_decide_with_raw,
    coach_stream_raw_events,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_INVALID_SELECTION_RETRY_NOTE = (
    "If you set selected_assignment_id, it MUST be one of the candidate ids (or null). "
    "Do not invent ids."
)


@dataclass
class PreparedChatContext:
    user_id: str
    user_text: str
    plan_items: list[PlanItem]
    assignments_by_id: dict[str, Any]
    assignment_status_map: dict[str, str]
    candidates: list[dict]
    reference_assignments: list[dict]
    last_selected_plan_item_id: str | None
    last_selected_assignment_id: str | None
    visible_chat_is_empty: bool
    ack: bool
    short_followup: bool
    fresh_visible_chat_turn: bool
    lang_hint: str
    conversation_history: str
    conversation_summary: str
    user_state_obj: dict[str, Any]
    user_state_json: str
    runtime_notes: list[str]
    export_source: dict[str, Any]

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
    return _best_candidate_id_for_text(user_text=user_text, candidates=candidates)


def _is_overview_request(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(
        phrase in t
        for phrase in [
            "what do i have",
            "what else",
            "what subjects",
            "what's coming up",
            "whats coming up",
            "overview",
            "vad har jag",
            "vad har jag kvar",
            "på gång",
            "vilka ämnen",
            "överblick",
            "overblick",
        ]
    )


def _is_specific_task_request(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or _is_overview_request(t):
        return False
    return any(
        phrase in t
        for phrase in [
            "help me",
            "start",
            "continue",
            "work on",
            "do now",
            "choose",
            "pick",
            "hjälp",
            "hjalp",
            "börja",
            "borja",
            "fortsätt",
            "fortsatt",
            "välj",
            "valj",
        ]
    )


def _is_greeting(text: str) -> bool:
    t = (text or "").strip().lower().strip(".!?")
    return t in {
        "hej",
        "hej hej",
        "hejsan",
        "hi",
        "hello",
        "hey",
        "tjena",
        "hallå",
        "halla",
    }


def _is_reopen_request(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(
        phrase in t
        for phrase in [
            "reopen",
            "open again",
            "continue it again",
            "work on it again",
            "öppna",
            "oppna",
            "öppna den igen",
            "oppna den igen",
            "öppna engelskan igen",
            "oppna engelskan igen",
            "fortsätt med den",
            "fortsatt med den",
            "jobba vidare på den",
            "öppna uppgiften igen",
            "open the assignment again",
        ]
    )


def _last_assistant_text(history: list[dict[str, Any]]) -> str:
    for item in reversed(history):
        if item.get("role") == "assistant":
            text = item.get("text")
            if isinstance(text, str):
                return text.strip()
    return ""


def _looks_like_short_followup_answer(*, user_text: str, last_assistant_text: str) -> bool:
    ut = (user_text or "").strip()
    if not ut or _is_greeting(ut) or _is_overview_request(ut) or _is_specific_task_request(ut):
        return False
    if len(ut) > 40 or len(ut.split()) > 4:
        return False
    lat = (last_assistant_text or "").strip().lower()
    if "?" not in lat:
        return False
    return any(
        marker in lat
        for marker in [
            "vilken",
            "vad",
            "which",
            "what",
            "eller",
            " or ",
            "vill du",
            "do you want",
            "focus on",
        ]
    )


def _is_likely_off_scope_request(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    assignment_anchors = [
        "assignment",
        "classroom",
        "homework",
        "uppgift",
        "läxa",
        "laxa",
        "teacher",
        "lärare",
        "larare",
        "upload",
        "uploaded",
        "paste",
        "klistra in",
    ]
    if any(anchor in t for anchor in assignment_anchors):
        return False
    off_scope_markers = [
        "generate an image",
        "create an image",
        "make an image",
        "genera en bild",
        "generera en bild",
        "skapa en bild",
        "mello",
        "melodifestival",
        "måns zelmerlöw",
        "mans zelmerlow",
        "carola",
        "what does fuck mean",
        "vad betyder fuck",
        "svordom",
        "swear word",
        "curse word",
        "who won",
        "vem vann",
    ]
    return any(marker in t for marker in off_scope_markers)


def _best_candidate_id_for_text(*, user_text: str, candidates: list[dict]) -> Optional[str]:
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


def _detect_lang_hint(s: str) -> str:
    import re

    s2 = s.lower()
    if any(ch in s2 for ch in "åäö"):
        return "sv"
    words = re.sub(r"[^a-zåäö]+", " ", s2).split()
    if any(w in words for w in ["hej", "tack", "okej", "klar", "färdig", "borja", "börja", "engelska", "idag"]):
        return "sv"
    return "en"


async def _prepare_chat_context(
    payload: ChatSendRequest,
    *,
    user_id: str,
    export_source: dict[str, Any],
) -> PreparedChatContext:
    user_text = (payload.user_message or "").strip()
    if not user_text:
        logger.warning("chat_send_400 user_message_required user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="user_message required")

    plan_items = payload.current_plan.items if (payload.current_plan and payload.current_plan.items) else []
    visible_chat_is_empty = bool(payload.visible_chat_is_empty)
    lang_hint = _detect_lang_hint(user_text)

    if payload.current_plan and payload.current_plan.items:
        status_map = get_assignment_status_map(user_id=user_id)
        if status_map:
            for it in plan_items:
                sid = it.sourceAssignmentId
                if sid and sid in status_map:
                    it.status = status_map[sid]

    assignments, _meta = await select_assignments(user_id)
    assignments_by_id = {a.id: a for a in assignments}
    last_selected_plan_item_id = get_last_selected_plan_item_id(user_id=user_id)
    last_selected_assignment_id = get_last_selected_assignment_id(user_id=user_id)
    assignment_status_map = get_assignment_status_map(user_id=user_id)

    plan_assignment_ids = {it.sourceAssignmentId for it in plan_items if it.sourceAssignmentId}
    base_assignments = [
        a
        for a in assignments
        if (not plan_assignment_ids or a.id in plan_assignment_ids)
        and assignment_status_map.get(a.id) != "done"
    ]
    if not base_assignments:
        base_assignments = [a for a in assignments if assignment_status_map.get(a.id) != "done"]

    ut = user_text.strip().lower().strip(".!?")
    ack = ut in {"ja", "japp", "ok", "okej", "yes", "yep", "sure", "kör", "bra"}
    if ack and last_selected_assignment_id:
        candidate_assignments = [a for a in base_assignments if a.id == last_selected_assignment_id][:1]
        if not candidate_assignments:
            candidate_assignments = base_assignments[:12]
    else:
        candidate_assignments = base_assignments[:12]

    reference_pool: list[Any] = []
    if last_selected_assignment_id and last_selected_assignment_id in assignments_by_id:
        reference_pool.append(assignments_by_id[last_selected_assignment_id])
    reference_pool.extend(a for a in assignments if assignment_status_map.get(a.id) == "done")
    seen_reference_ids: set[str] = set()
    reference_assignments: list[dict] = []
    active_candidate_ids = {a.id for a in candidate_assignments}

    candidates: list[dict] = []
    for a in candidate_assignments:
        desc = ""
        due_soon = False
        overdue = False
        due_in_days = None
        if isinstance(a.dueDate, str) and a.dueDate:
            try:
                dt = datetime.fromisoformat(a.dueDate.replace("Z", "+00:00"))
                due_in_days = (dt.date() - datetime.now(timezone.utc).date()).days
                due_soon = due_in_days <= 3
                overdue = due_in_days < 0
            except Exception:
                due_soon = False
                overdue = False
                due_in_days = None
        d = a.description
        if isinstance(d, str):
            desc = d.strip()[:1000]
        candidates.append(
            {
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
                "is_overdue": overdue,
                "due_in_days": due_in_days,
            }
        )

    for a in reference_pool:
        if a.id in active_candidate_ids or a.id in seen_reference_ids:
            continue
        seen_reference_ids.add(a.id)
        desc = ""
        if isinstance(a.description, str):
            desc = a.description.strip()[:1000]
        reference_assignments.append(
            {
                "id": a.id,
                "title": a.title,
                "courseName": a.courseName,
                "dueDate": a.dueDate,
                "estimatedMinutes": a.estimatedMinutes,
                "description": desc,
                "url": a.url,
                "status": assignment_status_map.get(a.id, "todo"),
                "is_last_selected": bool(last_selected_assignment_id and a.id == last_selected_assignment_id),
            }
        )
        if len(reference_assignments) >= 12:
            break

    hist = get_chat_history(user_id=user_id, limit=10)
    last_assistant_text = _last_assistant_text(hist)
    fresh_visible_chat_turn = visible_chat_is_empty and _is_greeting(user_text)
    prompt_history = [] if fresh_visible_chat_turn else hist
    conversation_history = "\n".join([f"{h['role']}: {h['text']}" for h in prompt_history])
    user_state_obj = get_user_state(user_id=user_id)
    conversation_summary = _sanitize_user_only_summary(str(user_state_obj.get("conversation_summary") or ""))
    if fresh_visible_chat_turn:
        conversation_summary = ""
        user_state_obj.pop("last_selected_plan_item_id", None)
        user_state_obj.pop("last_selected_assignment_id", None)
        user_state_obj.pop("conversation_summary", None)
    if conversation_summary:
        user_state_obj["conversation_summary"] = conversation_summary
    else:
        user_state_obj.pop("conversation_summary", None)
    user_state_json = json.dumps(user_state_obj, ensure_ascii=False)
    short_followup = _looks_like_short_followup_answer(
        user_text=user_text,
        last_assistant_text=last_assistant_text,
    )
    runtime_notes: list[str] = []
    if _is_likely_off_scope_request(user_text):
        runtime_notes.append(
            "The student's latest request appears off-scope unless it is clearly tied to an assignment in the active candidates, the reference assignments, or pasted/uploaded assignment instructions. If it is not tied to homework, politely refuse and redirect them back to Classroom or pasted/uploaded assignment text."
        )
    if fresh_visible_chat_turn:
        runtime_notes.append(
            "The visible chat is empty and the student started with a fresh greeting. Treat this turn as a new conversation opener. Do not continue a hidden previous thread unless the student explicitly asks to continue older work."
        )
    if short_followup:
        runtime_notes.append(
            "The student's latest message is likely answering your previous question. Continue the same thread. Do not restart with a new greeting and do not switch back to a general assignment overview unless the student explicitly asks for one."
        )

    return PreparedChatContext(
        user_id=user_id,
        user_text=user_text,
        plan_items=plan_items,
        assignments_by_id=assignments_by_id,
        assignment_status_map=assignment_status_map,
        candidates=candidates,
        reference_assignments=reference_assignments,
        last_selected_plan_item_id=last_selected_plan_item_id,
        last_selected_assignment_id=last_selected_assignment_id,
        visible_chat_is_empty=visible_chat_is_empty,
        ack=ack,
        short_followup=short_followup,
        fresh_visible_chat_turn=fresh_visible_chat_turn,
        lang_hint=lang_hint,
        conversation_history=conversation_history,
        conversation_summary=conversation_summary,
        user_state_obj=user_state_obj,
        user_state_json=user_state_json,
        runtime_notes=runtime_notes,
        export_source=export_source,
    )


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if value is None or value == "" or value == "-":
            continue
        out[key] = value
    return out


def _build_export_source(
    *,
    request: Optional[Request],
    ctx: AuthContext,
    route_path: str,
    transport: str,
    client_channel: str | None,
    client_platform: str | None,
    app_version: str | None,
    app_build: str | None,
) -> dict[str, Any]:
    inherited = dict(ctx.export_source or {})
    return _compact_dict(
        {
            "channel": client_channel or inherited.get("channel") or "api",
            "platform": client_platform or inherited.get("platform"),
            "app_version": app_version or inherited.get("app_version"),
            "build": app_build or inherited.get("build"),
            "route": route_path if request is not None else inherited.get("route", route_path),
            "transport": transport if request is not None else inherited.get("transport", transport),
            "request_id": get_request_id(),
        }
    )


def _build_debug_export_payload(
    *,
    prepared: PreparedChatContext,
    attempts: list[dict[str, Any]],
    assistant_text: str,
    best_next_action_id: str | None,
    selected_assignment_id: str | None,
    mark_done_assignment_id: str | None,
    reopen_assignment_id: str | None,
) -> dict[str, Any]:
    legacy_payload = {
        "user_message": prepared.user_text,
        "lang_hint": prepared.lang_hint,
        "conversation_history": prepared.conversation_history,
        "conversation_summary": prepared.conversation_summary,
        "user_state_json": prepared.user_state_json,
        "candidates": prepared.candidates,
        "attempts": attempts,
        "response": {
            "assistant_text": assistant_text,
            "best_next_action_id": best_next_action_id,
            "selected_assignment_id": selected_assignment_id,
            "mark_done_assignment_id": mark_done_assignment_id,
            "reopen_assignment_id": reopen_assignment_id,
        },
    }

    return {
        "source": prepared.export_source,
        "request": {
            "user_message": prepared.user_text,
            "lang_hint": prepared.lang_hint,
            "acknowledgement_message": prepared.ack,
            "visible_chat_is_empty": prepared.visible_chat_is_empty,
        },
        "context": {
            "conversation_history": prepared.conversation_history,
            "conversation_summary": prepared.conversation_summary,
            "user_state": prepared.user_state_obj,
            "candidates": prepared.candidates,
            "reference_assignments": prepared.reference_assignments,
            "last_selected_assignment_id": prepared.last_selected_assignment_id,
            "last_selected_plan_item_id": prepared.last_selected_plan_item_id,
            "runtime_notes": prepared.runtime_notes,
        },
        "model": {"attempts": attempts},
        "response": {
            "assistant_text": assistant_text,
            "best_next_action_id": best_next_action_id,
            "selected_assignment_id": selected_assignment_id,
            "mark_done_assignment_id": mark_done_assignment_id,
            "reopen_assignment_id": reopen_assignment_id,
        },
        # Temporary duplicate during rollout so existing workflows can keep using payload.
        "payload": legacy_payload,
    }


def _candidate_ids(prepared: PreparedChatContext) -> set[str]:
    return {str(c.get("id")) for c in prepared.candidates if isinstance(c.get("id"), str)}


def _reference_assignment_ids(prepared: PreparedChatContext) -> set[str]:
    return {
        str(c.get("id"))
        for c in prepared.reference_assignments
        if isinstance(c.get("id"), str)
    }


def _model_user_message(prepared: PreparedChatContext, *, extra_note: str = "") -> str:
    msg = prepared.user_text if not extra_note else f"{prepared.user_text}\n\nNOTE: {extra_note}"
    if prepared.ack and (prepared.last_selected_assignment_id or prepared.last_selected_plan_item_id):
        if prepared.last_selected_assignment_id in _reference_assignment_ids(prepared):
            msg = (
                f"{msg}\n\nNOTE: The student is acknowledging your previous suggestion about a reference assignment. "
                "If they want to work on that old assignment again, use reopen_assignment_id for it instead of switching to unrelated active tasks."
            )
        else:
            msg = f"{msg}\n\nNOTE: The student is acknowledging your previous suggestion. Continue the same task/thread; do not switch subjects."
    for note in prepared.runtime_notes:
        msg = f"{msg}\n\nNOTE: {note}"
    return msg


def _attempt_entry(prepared: PreparedChatContext, *, extra_note: str = "") -> dict[str, Any]:
    msg = _model_user_message(prepared, extra_note=extra_note)
    prompt = build_coach_prompt(
        user_message=msg,
        plan_items_json=json.dumps(prepared.candidates, ensure_ascii=False),
        reference_assignments_json=json.dumps(prepared.reference_assignments, ensure_ascii=False),
        conversation_history=prepared.conversation_history,
        conversation_summary=prepared.conversation_summary,
        user_state_json=prepared.user_state_json,
        visible_chat_is_empty=prepared.visible_chat_is_empty,
    )
    return {
        "extra_note": extra_note,
        "user_message_to_model": msg,
        "prompt": prompt,
    }


def _selected_assignment_id(
    prepared: PreparedChatContext,
    decision: CoachDecision,
    *,
    allow_invalid: bool,
) -> str | None:
    selected_assignment_id = getattr(decision, "selected_assignment_id", None)
    if not selected_assignment_id and decision.selected_plan_item_id:
        pi = next((it for it in prepared.plan_items if it.id == decision.selected_plan_item_id), None)
        if pi and pi.sourceAssignmentId:
            selected_assignment_id = pi.sourceAssignmentId
        elif decision.selected_plan_item_id in _candidate_ids(prepared):
            # Some model responses still place an assignment id in the legacy field.
            selected_assignment_id = decision.selected_plan_item_id

    if selected_assignment_id and selected_assignment_id not in _candidate_ids(prepared):
        if allow_invalid:
            logger.warning(
                "chat_stream_invalid_selection user_id=%s selected_assignment_id=%s",
                prepared.user_id,
                selected_assignment_id,
            )
            return None
        raise HTTPException(status_code=502, detail="OpenAI returned invalid selection")

    if not selected_assignment_id and _is_specific_task_request(prepared.user_text):
        inferred = _best_candidate_id_for_text(
            user_text=prepared.user_text,
            candidates=prepared.candidates,
        )
        if inferred and inferred in _candidate_ids(prepared):
            decision.selected_assignment_id = inferred
            decision.selected_plan_item_id = None
            return inferred
    return selected_assignment_id


def _reopen_assignment_id(prepared: PreparedChatContext, decision: CoachDecision) -> str | None:
    reopen_assignment_id = getattr(decision, "reopen_assignment_id", None)
    if reopen_assignment_id and reopen_assignment_id in _reference_assignment_ids(prepared):
        return reopen_assignment_id
    if reopen_assignment_id:
        return None
    if prepared.last_selected_assignment_id and prepared.ack:
        if prepared.last_selected_assignment_id in _reference_assignment_ids(prepared):
            decision.reopen_assignment_id = prepared.last_selected_assignment_id
            return prepared.last_selected_assignment_id
    if _is_reopen_request(prepared.user_text):
        inferred = _best_candidate_id_for_text(
            user_text=prepared.user_text,
            candidates=prepared.reference_assignments,
        )
        if inferred and inferred in _reference_assignment_ids(prepared):
            decision.reopen_assignment_id = inferred
            return inferred
    return None


def _has_invalid_selected_assignment(prepared: PreparedChatContext, decision: CoachDecision) -> bool:
    selected_assignment_id = getattr(decision, "selected_assignment_id", None)
    if not selected_assignment_id and decision.selected_plan_item_id:
        pi = next((it for it in prepared.plan_items if it.id == decision.selected_plan_item_id), None)
        if pi and pi.sourceAssignmentId:
            selected_assignment_id = pi.sourceAssignmentId
        elif decision.selected_plan_item_id in _candidate_ids(prepared):
            selected_assignment_id = decision.selected_plan_item_id
    return bool(selected_assignment_id and selected_assignment_id not in _candidate_ids(prepared))


def _attach_decision_metadata(attempts: list[dict[str, Any]], decision: CoachDecision) -> None:
    for attempt in attempts:
        attempt["decision"] = {
            "selected_assignment_id": getattr(decision, "selected_assignment_id", None),
            "reopen_assignment_id": getattr(decision, "reopen_assignment_id", None),
            "selected_plan_item_id": getattr(decision, "selected_plan_item_id", None),
            "mark_done_assignment_id": getattr(decision, "mark_done_assignment_id", None),
            "mark_done_plan_item_id": getattr(decision, "mark_done_plan_item_id", None),
            "reply_language": getattr(decision, "reply_language", None),
        }


async def _finalize_coach_decision(
    prepared: PreparedChatContext,
    decision: CoachDecision,
    *,
    retry_invalid_selection: Any = None,
) -> tuple[CoachDecision, str | None, str | None]:
    if _has_invalid_selected_assignment(prepared, decision):
        if retry_invalid_selection is None:
            logger.warning("chat_stream_invalid_selection user_id=%s", prepared.user_id)
        else:
            decision = await retry_invalid_selection(_INVALID_SELECTION_RETRY_NOTE)

    selected_assignment_id = _selected_assignment_id(
        prepared,
        decision,
        allow_invalid=retry_invalid_selection is None,
    )
    reopen_assignment_id = _reopen_assignment_id(prepared, decision)
    if reopen_assignment_id and not selected_assignment_id:
        selected_assignment_id = reopen_assignment_id
        decision.selected_assignment_id = reopen_assignment_id
        decision.selected_plan_item_id = None
    return decision, selected_assignment_id, reopen_assignment_id


def _build_chat_response(
    prepared: PreparedChatContext,
    decision: CoachDecision,
    *,
    attempts: list[dict[str, Any]],
    selected_assignment_id: str | None,
    reopen_assignment_id: str | None,
) -> ChatSendResponse:
    if prepared.ack and prepared.last_selected_assignment_id and not selected_assignment_id:
        if prepared.last_selected_assignment_id in _candidate_ids(prepared):
            selected_assignment_id = prepared.last_selected_assignment_id
            decision.selected_assignment_id = prepared.last_selected_assignment_id
    if reopen_assignment_id:
        prepared.assignment_status_map[reopen_assignment_id] = "todo"
        for item in prepared.plan_items:
            if item.sourceAssignmentId == reopen_assignment_id and item.status == "done":
                item.status = "todo"

    mark_done_assignment_id = getattr(decision, "mark_done_assignment_id", None)
    if not mark_done_assignment_id and _is_completion_utterance(prepared.user_text):
        inferred = _best_candidate_id_for_text(user_text=prepared.user_text, candidates=prepared.candidates)
        if inferred:
            mark_done_assignment_id = inferred
            decision.mark_done_assignment_id = inferred

    best_next_action = None
    if selected_assignment_id:
        best_next_action = next(
            (it for it in prepared.plan_items if it.sourceAssignmentId == selected_assignment_id and it.status != "done"),
            None,
        )
        if best_next_action is None:
            assignment = prepared.assignments_by_id.get(str(selected_assignment_id))
            if assignment is not None:
                mins = assignment.estimatedMinutes if getattr(assignment, "estimatedMinutes", None) is not None else 15
                best_next_action = PlanItem(
                    id=f"{assignment.id}-1",
                    title=f"Start {assignment.title}: {mins} min",
                    dueDate=getattr(assignment, "dueDate", None),
                    estimatedMinutes=mins,
                    status=prepared.assignment_status_map.get(assignment.id, "todo"),
                    sourceAssignmentId=assignment.id,
                    attachments=getattr(assignment, "attachments", None),
                )

    if not mark_done_assignment_id and decision.mark_done_plan_item_id:
        done_item = next((it for it in prepared.plan_items if it.id == decision.mark_done_plan_item_id), None)
        if done_item and done_item.sourceAssignmentId:
            mark_done_assignment_id = done_item.sourceAssignmentId

    text = (decision.assistant_text or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI returned empty response")

    now_ts = int(time.time())
    persist_chat_turn(
        user_id=prepared.user_id,
        user_text=prepared.user_text,
        assistant_text=text,
        now_ts=now_ts,
        conversation_summary=_update_rolling_summary(
            str(prepared.user_state_obj.get("conversation_summary") or ""),
            prepared.user_text,
            text,
        ),
        language_preference=(
            decision.reply_language
            if isinstance(decision.reply_language, str) and decision.reply_language == prepared.lang_hint
            else None
        ),
        selected_plan_item_id=(best_next_action.id if best_next_action is not None else None),
        selected_assignment_id=selected_assignment_id,
        mark_done_assignment_id=mark_done_assignment_id,
        reopen_assignment_id=reopen_assignment_id,
    )

    assistant_message = ChatMessage(id=new_id(), role="assistant", text=text, timestamp=iso_now())

    try:
        _attach_decision_metadata(attempts, decision)
        export_chat_trace(
            user_id=prepared.user_id,
            payload=_build_debug_export_payload(
                prepared=prepared,
                attempts=attempts,
                assistant_text=text,
                best_next_action_id=(best_next_action.id if best_next_action else None),
                selected_assignment_id=selected_assignment_id,
                mark_done_assignment_id=mark_done_assignment_id,
                reopen_assignment_id=reopen_assignment_id,
            ),
        )
    except Exception:
        pass

    return ChatSendResponse(
        assistant_message=assistant_message,
        best_next_action=best_next_action,
    )


def _stream_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


@router.post("/chat/send", response_model=ChatSendResponse)
async def chat_send(
    payload: ChatSendRequest,
    request: Request,
    x_client_channel: Optional[str] = Header(default=None, alias="X-Client-Channel"),
    x_client_platform: Optional[str] = Header(default=None, alias="X-Client-Platform"),
    x_app_version: Optional[str] = Header(default=None, alias="X-App-Version"),
    x_app_build: Optional[str] = Header(default=None, alias="X-App-Build"),
    ctx: AuthContext = Depends(require_user_id),
) -> ChatSendResponse:
    return await _chat_send_impl(
        payload,
        ctx=ctx,
        request=request,
        client_channel=x_client_channel,
        client_platform=x_client_platform,
        app_version=x_app_version,
        app_build=x_app_build,
    )


async def _chat_send_impl(
    payload: ChatSendRequest,
    *,
    ctx: AuthContext,
    request: Optional[Request],
    client_channel: Optional[str],
    client_platform: Optional[str],
    app_version: Optional[str],
    app_build: Optional[str],
) -> ChatSendResponse:
    _require_openai()
    prepared = await _prepare_chat_context(
        payload,
        user_id=ctx.user_id,
        export_source=_build_export_source(
            request=request,
            ctx=ctx,
            route_path="/chat/send",
            transport="http",
            client_channel=client_channel,
            client_platform=client_platform,
            app_version=app_version,
            app_build=app_build,
        ),
    )

    async def _call_coach(extra_note: str = ""):
        attempt = _attempt_entry(prepared, extra_note=extra_note)
        attempts.append(attempt)
        # Only capture raw model output when debug export is enabled. This keeps
        # the default path compatible with tests that monkeypatch coach_decide.
        from app.core.config import get_settings

        settings = get_settings()
        if settings.debug_export_enabled:
            decision, raw = await coach_decide_with_raw(
                user_message=attempt["user_message_to_model"],
                plan_items_json=json.dumps(prepared.candidates, ensure_ascii=False),
                reference_assignments_json=json.dumps(prepared.reference_assignments, ensure_ascii=False),
                conversation_history=prepared.conversation_history,
                conversation_summary=prepared.conversation_summary,
                user_state_json=prepared.user_state_json,
                visible_chat_is_empty=prepared.visible_chat_is_empty,
            )
            attempts[-1]["raw_model_output"] = raw
            return decision

        return await coach_decide(
            user_message=attempt["user_message_to_model"],
            plan_items_json=json.dumps(prepared.candidates, ensure_ascii=False),
            reference_assignments_json=json.dumps(prepared.reference_assignments, ensure_ascii=False),
            conversation_history=prepared.conversation_history,
            conversation_summary=prepared.conversation_summary,
            user_state_json=prepared.user_state_json,
            visible_chat_is_empty=prepared.visible_chat_is_empty,
        )

    # Call coach; retry once if the model fails to select a valid candidate id.
    attempts: list[dict] = []
    try:
        decision = await _call_coach()
    except (ValueError, ValidationError) as e:
        logger.warning("chat_send_openai_invalid_json error=%s", type(e).__name__)
        raise HTTPException(status_code=502, detail="OpenAI returned invalid JSON")
    except (httpx.HTTPError, RuntimeError, TimeoutError) as e:
        logger.warning("chat_send_openai_unavailable error=%s", type(e).__name__)
        raise HTTPException(status_code=503, detail="OpenAI unavailable")

    try:
        decision, selected_assignment_id, reopen_assignment_id = await _finalize_coach_decision(
            prepared,
            decision,
            retry_invalid_selection=_call_coach,
        )
    except (ValueError, ValidationError) as e:
        logger.warning("chat_send_openai_invalid_json error=%s", type(e).__name__)
        raise HTTPException(status_code=502, detail="OpenAI returned invalid JSON")
    except (httpx.HTTPError, RuntimeError, TimeoutError) as e:
        logger.warning("chat_send_openai_unavailable error=%s", type(e).__name__)
        raise HTTPException(status_code=503, detail="OpenAI unavailable")

    return _build_chat_response(
        prepared,
        decision,
        attempts=attempts,
        selected_assignment_id=selected_assignment_id,
        reopen_assignment_id=reopen_assignment_id,
    )


@router.post("/chat/send_stream")
async def chat_send_stream(
    payload: ChatSendRequest,
    request: Request,
    x_client_channel: Optional[str] = Header(default=None, alias="X-Client-Channel"),
    x_client_platform: Optional[str] = Header(default=None, alias="X-Client-Platform"),
    x_app_version: Optional[str] = Header(default=None, alias="X-App-Version"),
    x_app_build: Optional[str] = Header(default=None, alias="X-App-Build"),
    ctx: AuthContext = Depends(require_user_id),
) -> StreamingResponse:
    _require_openai()
    prepared = await _prepare_chat_context(
        payload,
        user_id=ctx.user_id,
        export_source=_build_export_source(
            request=request,
            ctx=ctx,
            route_path="/chat/send_stream",
            transport="stream",
            client_channel=x_client_channel,
            client_platform=x_client_platform,
            app_version=x_app_version,
            app_build=x_app_build,
        ),
    )

    async def event_stream():
        attempts: list[dict[str, Any]] = []
        parser = AssistantTextJSONStreamParser()
        formatter = BubbleStreamFormatter()
        raw_output_parts: list[str] = []

        yield _stream_event({"type": "typing_started"})

        try:
            attempt = _attempt_entry(prepared)
            attempts.append(attempt)

            async for event in coach_stream_raw_events(
                user_message=attempt["user_message_to_model"],
                plan_items_json=json.dumps(prepared.candidates, ensure_ascii=False),
                reference_assignments_json=json.dumps(prepared.reference_assignments, ensure_ascii=False),
                conversation_history=prepared.conversation_history,
                conversation_summary=prepared.conversation_summary,
                user_state_json=prepared.user_state_json,
                visible_chat_is_empty=prepared.visible_chat_is_empty,
            ):
                if event.get("type") != "response.output_text.delta":
                    continue
                raw_delta = str(event.get("delta") or "")
                if not raw_delta:
                    continue
                raw_output_parts.append(raw_delta)
                assistant_delta = parser.feed(raw_delta)
                if not assistant_delta:
                    continue
                for bubble_event in formatter.feed(assistant_delta):
                    yield _stream_event(bubble_event)

            raw_output = "".join(raw_output_parts).strip()
            attempts[-1]["raw_model_output"] = raw_output
            decision = CoachDecision.model_validate(_parse_json_object_relaxed(raw_output))
            decision, selected_assignment_id, reopen_assignment_id = await _finalize_coach_decision(
                prepared,
                decision,
            )
            response = _build_chat_response(
                prepared,
                decision,
                attempts=attempts,
                selected_assignment_id=selected_assignment_id,
                reopen_assignment_id=reopen_assignment_id,
            )

            for bubble_event in formatter.finish():
                yield _stream_event(bubble_event)
            if response.best_next_action is not None:
                yield _stream_event(
                    {
                        "type": "best_next_action",
                        "best_next_action": response.best_next_action.model_dump(mode="json"),
                    }
                )
            yield _stream_event({"type": "turn_completed"})
        except (ValueError, ValidationError) as e:
            logger.warning("chat_send_stream_invalid_json error=%s", type(e).__name__)
            for bubble_event in formatter.finish():
                yield _stream_event(bubble_event)
            yield _stream_event({"type": "error", "message": "OpenAI returned invalid JSON"})
        except (httpx.HTTPError, RuntimeError, TimeoutError) as e:
            logger.warning("chat_send_stream_openai_unavailable error=%s", type(e).__name__)
            for bubble_event in formatter.finish():
                yield _stream_event(bubble_event)
            yield _stream_event({"type": "error", "message": "OpenAI unavailable"})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


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


