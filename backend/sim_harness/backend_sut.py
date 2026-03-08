from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx


@dataclass
class BackendTurnResult:
    assistant_text: str
    assistant_bubbles: List[str]
    selected_assignment_id: Optional[str]
    marked_done_assignment_ids: List[str]
    raw_response_json: Dict[str, Any]


def _plan_from_assignments(assignments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a minimal current_plan payload for /chat/send.
    The backend uses this to bound assignment ids; it still fetches assignments via select_assignments.
    """
    items: List[Dict[str, Any]] = []
    for a in assignments:
        aid = a.get("id")
        title = a.get("title") or "Assignment"
        if not isinstance(aid, str) or not aid:
            continue
        items.append(
            {
                "id": f"{aid}-1",
                "title": f"Start {title}",
                "dueDate": a.get("dueDate") if isinstance(a.get("dueDate"), str) else None,
                "estimatedMinutes": a.get("estimatedMinutes") if isinstance(a.get("estimatedMinutes"), int) else 15,
                "status": "todo",
                "sourceAssignmentId": aid,
            }
        )
    if not items:
        # /chat/send requires at least one item.
        items = [
            {
                "id": "dummy-1",
                "title": "Start something",
                "dueDate": None,
                "estimatedMinutes": 15,
                "status": "todo",
                "sourceAssignmentId": "dummy",
            }
        ]
    return {"weekStart": "2026-01-13", "items": items}


def _extract_selected_assignment_id(chat_send_json: Dict[str, Any]) -> Optional[str]:
    bna = chat_send_json.get("best_next_action")
    if not isinstance(bna, dict):
        return None
    sid = bna.get("sourceAssignmentId")
    return str(sid) if isinstance(sid, str) and sid else None


def _extract_selected_assignment_id_from_stream(events: List[Dict[str, Any]]) -> Optional[str]:
    for event in events:
        if event.get("type") != "best_next_action":
            continue
        best = event.get("best_next_action")
        if not isinstance(best, dict):
            continue
        sid = best.get("sourceAssignmentId")
        if isinstance(sid, str) and sid:
            return sid
    return None


async def run_backend_inprocess_turn(
    *,
    client: httpx.AsyncClient,
    token: str,
    user_message: str,
    assignments: List[Dict[str, Any]],
    clear_assignment_status_on_reset: bool = True,
    clear_preferences_on_reset: bool = True,
    do_reset: bool = False,
    user_id: str,
) -> BackendTurnResult:
    """
    Execute a single /chat/send turn against an in-process FastAPI app via httpx.
    This exercises the real route + SQLite persistence.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Client-Channel": "sim_harness",
        "X-Client-Platform": "backend",
    }

    if do_reset:
        qs = []
        if clear_assignment_status_on_reset:
            qs.append("clear_assignment_status=true")
        if clear_preferences_on_reset:
            qs.append("clear_preferences=true")
        q = ("?" + "&".join(qs)) if qs else ""
        r0 = await client.post(f"/chat/reset{q}", headers=headers)
        r0.raise_for_status()

    payload = {
        "user_message": user_message,
        "current_plan": _plan_from_assignments(assignments),
    }
    r = await client.post("/chat/send", headers=headers, json=payload)
    r.raise_for_status()
    data = r.json()

    assistant_text = ""
    am = data.get("assistant_message")
    if isinstance(am, dict) and isinstance(am.get("text"), str):
        assistant_text = am["text"]

    # Mark-done ids: read persisted assignment_status map (in-process only).
    marked_done: List[str] = []
    try:
        from app.core.db import get_assignment_status_map

        m = get_assignment_status_map(user_id=user_id)
        marked_done = [k for k, v in m.items() if v == "done"]
    except Exception:
        marked_done = []

    return BackendTurnResult(
        assistant_text=assistant_text,
        assistant_bubbles=[assistant_text] if assistant_text else [],
        selected_assignment_id=_extract_selected_assignment_id(data),
        marked_done_assignment_ids=marked_done,
        raw_response_json=data,
    )


async def run_backend_inprocess_stream_turn(
    *,
    client: httpx.AsyncClient,
    token: str,
    user_message: str,
    assignments: List[Dict[str, Any]],
    clear_assignment_status_on_reset: bool = True,
    clear_preferences_on_reset: bool = True,
    do_reset: bool = False,
    user_id: str,
) -> BackendTurnResult:
    """
    Execute a single /chat/send_stream turn and collect streamed bubble events.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Client-Channel": "sim_harness",
        "X-Client-Platform": "backend",
    }

    if do_reset:
        qs = []
        if clear_assignment_status_on_reset:
            qs.append("clear_assignment_status=true")
        if clear_preferences_on_reset:
            qs.append("clear_preferences=true")
        q = ("?" + "&".join(qs)) if qs else ""
        r0 = await client.post(f"/chat/reset{q}", headers=headers)
        r0.raise_for_status()

    payload = {
        "user_message": user_message,
        "current_plan": _plan_from_assignments(assignments),
    }

    events: List[Dict[str, Any]] = []
    messages_by_id: Dict[str, str] = {}
    completion_order: List[str] = []

    async with client.stream("POST", "/chat/send_stream", headers=headers, json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            trimmed = (line or "").strip()
            if not trimmed:
                continue
            event = json.loads(trimmed)
            events.append(event)
            event_type = event.get("type")
            if event_type == "message_started":
                mid = event.get("message_id")
                if isinstance(mid, str) and mid:
                    messages_by_id[mid] = ""
            elif event_type == "message_delta":
                mid = event.get("message_id")
                delta = event.get("delta")
                if isinstance(mid, str) and mid and isinstance(delta, str):
                    messages_by_id[mid] = messages_by_id.get(mid, "") + delta
            elif event_type == "message_completed":
                mid = event.get("message_id")
                if isinstance(mid, str) and mid:
                    completion_order.append(mid)
            elif event_type == "error":
                msg = event.get("message")
                detail = str(msg) if isinstance(msg, str) and msg else "stream_error"
                raise RuntimeError(detail)

    assistant_bubbles = [messages_by_id[mid] for mid in completion_order if messages_by_id.get(mid)]
    assistant_text = "\n\n".join(assistant_bubbles)

    marked_done: List[str] = []
    try:
        from app.core.db import get_assignment_status_map

        m = get_assignment_status_map(user_id=user_id)
        marked_done = [k for k, v in m.items() if v == "done"]
    except Exception:
        marked_done = []

    return BackendTurnResult(
        assistant_text=assistant_text,
        assistant_bubbles=assistant_bubbles,
        selected_assignment_id=_extract_selected_assignment_id_from_stream(events),
        marked_done_assignment_ids=marked_done,
        raw_response_json={"events": events},
    )


def write_fixture_assignments(*, fixture_path: Path, assignments: List[Dict[str, Any]]) -> None:
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(assignments, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_backend_env(
    *,
    run_dir: Path,
    user_id: str,
    assignments: List[Dict[str, Any]],
    offline_deterministic: bool = True,
) -> Tuple[str, Path]:
    """
    Prepare env for an in-process backend instance:
    - isolate SQLite per run
    - provide per-run fixture assignments via ASSIGNMENTS_FIXTURE_PATH
    Returns (sqlite_path, fixture_path).
    """
    sqlite_path = run_dir / f"backend_{user_id}.db"
    fixture_path = run_dir / f"assignments_{user_id}.json"
    os.environ["SQLITE_PATH"] = str(sqlite_path)
    os.environ["ASSIGNMENTS_FIXTURE_PATH"] = str(fixture_path)
    if offline_deterministic:
        # Make the in-process backend deterministic and offline.
        # Note: when not under pytest, get_settings() reads .env; env vars should override it.
        os.environ["DEBUG_EXPORT_ENABLED"] = "false"
        os.environ["OPENAI_API_KEY"] = "test-key"  # bypass _require_openai gate
        os.environ.setdefault("SESSION_SECRET", "test-secret")
    else:
        # Real OpenAI mode: do not override OPENAI_API_KEY or DEBUG_EXPORT_ENABLED.
        # Ensure we have a session secret so we can issue deterministic session tokens locally.
        os.environ.setdefault("SESSION_SECRET", "test-secret")
    write_fixture_assignments(fixture_path=fixture_path, assignments=assignments)
    return str(sqlite_path), fixture_path


