from __future__ import annotations

import json
import re
import httpx

from app.core.config import get_settings
from app.services.prompts import load_text, render_template
from app.models.agent import CoachDecision


OPENAI_BASE_URL = "https://api.openai.com/v1"

_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")


def _parse_json_object_relaxed(text: str) -> dict:
    """
    Best-effort parse of a JSON object from model output.
    Accepts code fences or extra surrounding text by extracting the outermost {...}.
    """
    text = text.strip()
    # Strip common code fences.
    if text.startswith("```"):
        text = text.strip("`")
    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise ValueError("no_json_object_found")
    return json.loads(m.group(0))


async def plan_week(assignments_json: str, week_start: str) -> str:
    """
    Returns raw text from the model (expected to be JSON, but caller must validate/fallback).
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    system_prompt = load_text("plan_system.txt")
    user_prompt_template = load_text("plan_user.txt")
    user_prompt = render_template(
        user_prompt_template,
        {
            "week_start": week_start,
            "assignments_json": assignments_json,
        },
    )
    prompt = f"{system_prompt}\n\n{user_prompt}\n"

    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    payload = {"model": settings.openai_model, "input": prompt}

    async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
        r = await client.post(f"{OPENAI_BASE_URL}/responses", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    # Responses API: best-effort extraction of text.
    output = data.get("output", [])
    texts: list[str] = []
    for item in output:
        for c in item.get("content", []) or []:
            if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                texts.append(c["text"])
    if not texts:
        raise RuntimeError("OpenAI response missing text")
    return "\n".join(texts).strip()


async def coach_decide(
    *,
    user_message: str,
    plan_items_json: str,
    assignment_instructions: str,
    conversation_history: str = "",
    user_state_json: str = "",
) -> CoachDecision:
    decision, _raw = await coach_decide_with_raw(
        user_message=user_message,
        plan_items_json=plan_items_json,
        assignment_instructions=assignment_instructions,
        conversation_history=conversation_history,
        user_state_json=user_state_json,
    )
    return decision


async def coach_decide_with_raw(
    *,
    user_message: str,
    plan_items_json: str,
    assignment_instructions: str,
    conversation_history: str = "",
    conversation_summary: str = "",
    user_state_json: str = "",
) -> tuple[CoachDecision, str]:
    """
    Like coach_decide(), but also returns the raw model output text.
    Useful for debug exports / tracing.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    system_prompt = load_text("coach_system.txt")
    user_prompt_template = load_text("coach_user.txt")
    user_prompt = render_template(
        user_prompt_template,
        {
            "user_message": user_message,
            "plan_items_json": plan_items_json,
            "assignment_instructions": assignment_instructions,
            "conversation_history": conversation_history,
            "conversation_summary": conversation_summary,
            "user_state_json": user_state_json,
        },
    )
    prompt = f"{system_prompt}\n\n{user_prompt}\n"

    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    payload = {"model": settings.openai_model, "input": prompt}

    async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
        r = await client.post(f"{OPENAI_BASE_URL}/responses", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    output = data.get("output", [])
    texts: list[str] = []
    for item in output:
        for c in item.get("content", []) or []:
            if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                texts.append(c["text"])
    if not texts:
        raise RuntimeError("OpenAI response missing text")

    raw = "\n".join(texts).strip()
    obj = _parse_json_object_relaxed(raw)
    return CoachDecision.model_validate(obj), raw


def build_coach_prompt(
    *,
    user_message: str,
    plan_items_json: str,
    assignment_instructions: str,
    conversation_history: str = "",
    conversation_summary: str = "",
    user_state_json: str = "",
) -> str:
    system_prompt = load_text("coach_system.txt")
    user_prompt_template = load_text("coach_user.txt")
    user_prompt = render_template(
        user_prompt_template,
        {
            "user_message": user_message,
            "plan_items_json": plan_items_json,
            "assignment_instructions": assignment_instructions,
            "conversation_history": conversation_history,
            "conversation_summary": conversation_summary,
            "user_state_json": user_state_json,
        },
    )
    return f"{system_prompt}\n\n{user_prompt}\n"


