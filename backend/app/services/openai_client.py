from __future__ import annotations

import httpx

from app.core.config import get_settings


OPENAI_BASE_URL = "https://api.openai.com/v1"


async def plan_week(assignments_json: str, week_start: str) -> str:
    """
    Returns raw text from the model (expected to be JSON, but caller must validate/fallback).
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

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
    payload = {
        "model": "gpt-4.1-mini",
        "input": prompt,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
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


async def coach_text(user_message: str, best_next_action_title: str, minutes: int) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    prompt = (
        "You are a supportive study coach. Keep it short (1-3 sentences).\n"
        "You MUST include a concrete 10–20 minute starter for the next action.\n"
        f"Next action: {best_next_action_title}.\n"
        f"Starter duration: {minutes} minutes.\n"
        f"Student message: {user_message}\n"
    )

    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    payload = {"model": "gpt-4.1-mini", "input": prompt}

    async with httpx.AsyncClient(timeout=10.0) as client:
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


