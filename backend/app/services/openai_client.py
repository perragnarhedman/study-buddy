from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.prompts import load_text, render_template


OPENAI_BASE_URL = "https://api.openai.com/v1"


async def plan_week(assignments_json: str, week_start: str) -> str:
    """
    Returns raw text from the model (expected to be JSON, but caller must validate/fallback).
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Planning prompt intentionally kept inline for now (scope: coaching-only prompt modularization).
    prompt = (
        "You are a study planner. Output ONLY valid JSON for WeeklyPlan with fields:\n"
        '{ "weekStart": "YYYY-MM-DD", "items": [ { "id": "string", "title": "string", '
        '"dueDate": "ISO8601 or null", "estimatedMinutes": 10-20, "status": "todo|doing|done", '
        '"sourceAssignmentId": "string or null" } ] }\n'
        "Rules: max 15 items. Each estimatedMinutes between 10 and 20 inclusive.\n"
        f"weekStart must be {week_start}.\n"
        "Prefer titles: Start <assignment>: 15 min (optionally add (1/3) etc).\n"
        "Assignments JSON:\n"
        f"{assignments_json}\n"
    )

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


async def coach_text(
    user_message: str,
    best_next_action_title: str,
    minutes: int,
    *,
    tasks_context: str = "",
    plan_context: str = "",
    constraints_context: str = "",
) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    system_prompt_template = load_text("coach_system.txt")
    system_prompt = render_template(
        system_prompt_template,
        {"minutes": str(minutes), "best_next_action_title": best_next_action_title},
    )
    user_prompt_template = load_text("coach_user.txt")
    user_prompt = render_template(
        user_prompt_template,
        {
            "user_message": user_message,
            "best_next_action_title": best_next_action_title,
            "minutes": str(minutes),
            "tasks_context": tasks_context,
            "plan_context": plan_context,
            "constraints_context": constraints_context,
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
    return "\n".join(texts).strip()


