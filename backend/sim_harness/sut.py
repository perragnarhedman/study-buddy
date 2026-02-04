from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.models.agent import CoachDecision
from app.services.openai_client import build_coach_prompt, coach_decide_with_raw


def _truncate(s: Optional[str], n: int) -> str:
    if not isinstance(s, str):
        return ""
    return s.strip()[:n]


def build_candidates(assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in assignments:
        if not isinstance(a, dict):
            continue
        aid = a.get("id")
        title = a.get("title")
        course = a.get("courseName")
        if not (isinstance(aid, str) and isinstance(title, str) and isinstance(course, str)):
            continue
        out.append(
            {
                "id": aid,
                "title": title,
                "courseName": course,
                "dueDate": a.get("dueDate") if isinstance(a.get("dueDate"), str) else None,
                "estimatedMinutes": a.get("estimatedMinutes") if isinstance(a.get("estimatedMinutes"), int) else None,
                "description": _truncate(a.get("description"), 1000),
                "url": a.get("url") if isinstance(a.get("url"), str) else None,
                "status": "todo",
                "is_last_selected": False,
                "is_due_soon": False,
            }
        )
    return out


@dataclass
class SUTOutput:
    decision: CoachDecision
    raw_model_output: str
    prompt: str
    selected_assignment_id: Optional[str]


async def run_coach_openai(
    *,
    user_message: str,
    candidates: List[Dict[str, Any]],
    conversation_history: str,
    conversation_summary: str,
    user_state_json: str,
    assignment_instructions: str = "",
) -> SUTOutput:
    prompt = build_coach_prompt(
        user_message=user_message,
        plan_items_json=json.dumps(candidates, ensure_ascii=False),
        assignment_instructions=assignment_instructions,
        conversation_history=conversation_history,
        conversation_summary=conversation_summary,
        user_state_json=user_state_json,
    )
    decision, raw = await coach_decide_with_raw(
        user_message=user_message,
        plan_items_json=json.dumps(candidates, ensure_ascii=False),
        assignment_instructions=assignment_instructions,
        conversation_history=conversation_history,
        conversation_summary=conversation_summary,
        user_state_json=user_state_json,
    )
    sid = getattr(decision, "selected_assignment_id", None)
    return SUTOutput(decision=decision, raw_model_output=raw, prompt=prompt, selected_assignment_id=sid)


def run_coach_mock(*, user_message: str, candidates: List[Dict[str, Any]], lang: str) -> SUTOutput:
    """
    Deterministic coach for harness bring-up (no network).
    Very small heuristic: if user mentions a course name, select that candidate; else overview => no selection.
    """
    um = (user_message or "").lower()
    selected = None
    if any(k in um for k in ["what else", "what do i have", "vad mer", "vad har jag", "subjects", "ämnen"]):
        selected = None
    else:
        for c in candidates:
            title = str(c.get("title") or "").lower()
            course = str(c.get("courseName") or "").lower()
            if course and course in um:
                selected = str(c.get("id"))
                break
            if title and any(w in um for w in title.split()[:2]):
                selected = str(c.get("id"))
                break
        if selected is None and candidates:
            selected = str(candidates[0].get("id"))
    assistant_text = "Okej." if lang == "sv" else "OK."
    obj = {
        "assistant_text": assistant_text,
        "selected_assignment_id": selected,
        "mark_done_assignment_id": None,
        "selected_plan_item_id": None,
        "mark_done_plan_item_id": None,
        "reply_language": lang,
    }
    decision = CoachDecision.model_validate(obj)
    raw = json.dumps(obj, ensure_ascii=False)
    prompt = "(mock)"
    return SUTOutput(decision=decision, raw_model_output=raw, prompt=prompt, selected_assignment_id=selected)


