from __future__ import annotations

import json
import re
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.services.prompts import load_text, render_template
from app.models.agent import CoachDecision


OPENAI_BASE_URL = "https://api.openai.com/v1"

_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")


def _parse_json_object_relaxed(text: str) -> dict:
    """
    Best-effort parse of a JSON object from model output.
    Accepts extra surrounding text and code fences, but requires a single
    decodable JSON object.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    decoder = json.JSONDecoder()
    for m in _JSON_OBJ_RE.finditer(text):
        cand = m.group(0).strip()
        try:
            obj, idx = decoder.raw_decode(cand)
        except json.JSONDecodeError:
            continue
        if cand[idx:].strip():
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no_json_object_found")


def _extract_output_texts(data: dict) -> list[str]:
    output = data.get("output", [])
    texts: list[str] = []
    for item in output:
        for c in item.get("content", []) or []:
            if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                texts.append(c["text"])
    return texts


async def _responses_text(*, model: str, prompt: str, timeout_seconds: float, api_key: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "input": prompt}
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        r = await client.post(f"{OPENAI_BASE_URL}/responses", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    texts = _extract_output_texts(data)
    if not texts:
        raise RuntimeError("OpenAI response missing text")
    return "\n".join(texts).strip()


async def _responses_stream_events(
    *, model: str, prompt: str, timeout_seconds: float, api_key: str
) -> AsyncIterator[dict]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model,
        "input": prompt,
        "stream": True,
        "stream_options": {"include_obfuscation": False},
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with client.stream(
            "POST",
            f"{OPENAI_BASE_URL}/responses",
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()

            event_name: str | None = None
            data_lines: list[str] = []

            async for line in response.aiter_lines():
                if line == "":
                    if not data_lines:
                        event_name = None
                        continue
                    data = "\n".join(data_lines).strip()
                    data_lines = []
                    if data == "[DONE]":
                        break
                    payload_obj = json.loads(data)
                    if event_name and isinstance(payload_obj, dict) and "type" not in payload_obj:
                        payload_obj["type"] = event_name
                    yield payload_obj
                    event_name = None
                    continue

                if line.startswith("event:"):
                    event_name = line.partition(":")[2].strip()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line.partition(":")[2].lstrip())
                    continue


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

    return await _responses_text(
        model=settings.openai_plan_model,
        prompt=prompt,
        timeout_seconds=settings.openai_plan_timeout_seconds,
        api_key=settings.openai_api_key,
    )


async def coach_decide(
    *,
    user_message: str,
    plan_items_json: str,
    conversation_history: str = "",
    conversation_summary: str = "",
    user_state_json: str = "",
) -> CoachDecision:
    decision, _raw = await coach_decide_with_raw(
        user_message=user_message,
        plan_items_json=plan_items_json,
        conversation_history=conversation_history,
        conversation_summary=conversation_summary,
        user_state_json=user_state_json,
    )
    return decision


async def coach_decide_with_raw(
    *,
    user_message: str,
    plan_items_json: str,
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
            "conversation_history": conversation_history,
            "conversation_summary": conversation_summary,
            "user_state_json": user_state_json,
        },
    )
    prompt = f"{system_prompt}\n\n{user_prompt}\n"

    raw = await _responses_text(
        model=settings.openai_chat_model,
        prompt=prompt,
        timeout_seconds=settings.openai_chat_timeout_seconds,
        api_key=settings.openai_api_key,
    )
    obj = _parse_json_object_relaxed(raw)
    return CoachDecision.model_validate(obj), raw


def build_coach_prompt(
    *,
    user_message: str,
    plan_items_json: str,
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
            "conversation_history": conversation_history,
            "conversation_summary": conversation_summary,
            "user_state_json": user_state_json,
        },
    )
    return f"{system_prompt}\n\n{user_prompt}\n"


async def coach_stream_raw_events(
    *,
    user_message: str,
    plan_items_json: str,
    conversation_history: str = "",
    conversation_summary: str = "",
    user_state_json: str = "",
) -> AsyncIterator[dict]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    prompt = build_coach_prompt(
        user_message=user_message,
        plan_items_json=plan_items_json,
        conversation_history=conversation_history,
        conversation_summary=conversation_summary,
        user_state_json=user_state_json,
    )

    async for event in _responses_stream_events(
        model=settings.openai_chat_model,
        prompt=prompt,
        timeout_seconds=settings.openai_chat_timeout_seconds,
        api_key=settings.openai_api_key,
    ):
        yield event


