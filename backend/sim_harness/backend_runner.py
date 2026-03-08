from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from sim_harness.backend_sut import (
    prepare_backend_env,
    run_backend_inprocess_stream_turn,
    run_backend_inprocess_turn,
)
from sim_harness.evals import aggregate_suite
from sim_harness.models import Scenario
from sim_harness.scenarios import load_scenarios
from sim_harness.trace import TraceWriter, redact_for_trace


def _is_ack(text: str) -> bool:
    ut = (text or "").strip().lower().strip(".!?")
    return ut in {"ok", "okay", "okej", "ja", "yes", "yep", "sure"}


def _is_completion(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["i finished", "finished", "done", "completed", "submitted", "klar", "färdig", "fardig"])


def _detect_lang_hint(text: str) -> Optional[str]:
    s = (text or "").strip()
    if not s:
        return None
    s2 = s.lower()
    if any(ch in s2 for ch in "åäö"):
        return "sv"
    words = re.sub(r"[^a-zåäö]+", " ", s2).split()
    if any(w in words for w in ["hej", "tack", "okej", "klar", "färdig", "engelska", "idag", "vad", "jag"]):
        return "sv"
    return "en"


async def _install_deterministic_coach() -> None:
    """
    Patch the backend's coach_decide to be deterministic for integration testing.
    This keeps integration runs stable while still exercising the real /chat/send persistence path.
    """
    from app.models.agent import CoachDecision
    import app.routes.chat as chat_route

    async def deterministic_coach_decide(**kwargs) -> CoachDecision:
        user_message = str(kwargs.get("user_message") or "")
        user_message_lower = user_message.lower()
        plan_items_json = str(kwargs.get("plan_items_json") or "[]")
        reference_assignments_json = str(kwargs.get("reference_assignments_json") or "[]")
        selected: Optional[str] = None
        reopen: Optional[str] = None
        mark_done: Optional[str] = None

        # Let server rails handle mark-done inference; we intentionally do NOT set mark_done here.
        if _is_completion(user_message):
            selected = None
        elif _is_ack(user_message):
            # Intentionally drop selection to test server ack rails.
            selected = None
        elif "appears off-scope" in user_message_lower:
            selected = None
        elif "likely answering your previous question" in user_message_lower:
            selected = None
        elif "fresh greeting" in user_message_lower:
            selected = None
        elif any(phrase in user_message_lower for phrase in ["open again", "reopen", "öppna", "oppna", "continue that old"]):
            try:
                refs = json.loads(reference_assignments_json)
                if isinstance(refs, list) and refs:
                    first = refs[0]
                    if isinstance(first, dict) and isinstance(first.get("id"), str):
                        reopen = str(first["id"])
                        selected = reopen
            except Exception:
                reopen = None
                selected = None
        elif "reference assignment" in user_message_lower and _is_ack(user_message):
            try:
                refs = json.loads(reference_assignments_json)
                if isinstance(refs, list) and refs:
                    first = refs[0]
                    if isinstance(first, dict) and isinstance(first.get("id"), str):
                        reopen = str(first["id"])
                        selected = reopen
            except Exception:
                reopen = None
                selected = None
        else:
            try:
                items = json.loads(plan_items_json)
                if isinstance(items, list) and items:
                    first = items[0]
                    if isinstance(first, dict) and isinstance(first.get("id"), str):
                        selected = str(first["id"])
            except Exception:
                selected = None

        return CoachDecision(
            assistant_text="OK",
            reply_language="en",
            selected_assignment_id=selected,
            reopen_assignment_id=reopen,
            mark_done_assignment_id=mark_done,
        )

    async def deterministic_coach_decide_with_raw(**kwargs):
        d = await deterministic_coach_decide(**kwargs)
        raw = json.dumps(d.model_dump(), ensure_ascii=False)
        return d, raw

    # Patch both paths: /chat/send calls coach_decide normally, but may call coach_decide_with_raw
    # when DEBUG_EXPORT_ENABLED is true (developer env). We force debug off, but patch anyway.
    chat_route.coach_decide = deterministic_coach_decide  # type: ignore[assignment]
    chat_route.coach_decide_with_raw = deterministic_coach_decide_with_raw  # type: ignore[assignment]


async def run_backend_integration_suite(
    *,
    suite: str = "integration",
    output_dir: str = "sim_runs",
    max_turns: int = 6,
    use_openai_coach: bool = False,
    http_base_url: Optional[str] = None,
    session_token: Optional[str] = None,
) -> Dict[str, Any]:
    scenarios = load_scenarios(suite=suite)
    results: List[Dict[str, Any]] = []
    use_stream_endpoint = suite == "backend_stream"

    for sc in scenarios:
        tw = TraceWriter.create(output_dir=output_dir, scenario_id=sc.scenario_id)
        start = time.time()

        # Per-scenario isolated backend env + DB (in-process mode only).
        user_id = f"sim_{sc.scenario_id}_{tw.run_id}"
        if not http_base_url:
            prepare_backend_env(
                run_dir=tw.run_dir,
                user_id=user_id,
                assignments=sc.assignments,
                offline_deterministic=(not use_openai_coach),
            )

        from app.core.config import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        app = create_app() if not http_base_url else None

        # Patch coach to deterministic unless explicitly running with real OpenAI.
        if not use_openai_coach:
            await _install_deterministic_coach()

        from app.core.auth import issue_session_token

        token = session_token or issue_session_token(user_id)

        tw.write_event(
            {
                "type": "run_start",
                "run_id": tw.run_id,
                "scenario_id": sc.scenario_id,
                "scenario_title": sc.title,
                "sut": "backend_http" if http_base_url else "backend_inprocess",
                "transport": "send_stream" if use_stream_endpoint else "send",
                "use_openai_coach": use_openai_coach,
            }
        )

        # Turns (scripted only for now).
        script = list(sc.user_messages or [])
        if script:
            user_msg = script.pop(0)
        else:
            user_msg = sc.initial_user_message

        selected_any = False
        selected_by_turn: Dict[int, Optional[str]] = {}
        mark_done_by_turn: Dict[int, List[str]] = {}
        assistant_text_by_turn: Dict[int, str] = {}
        reply_language_by_turn: Dict[int, Optional[str]] = {}
        last_selected: Optional[str] = None
        failures: List[str] = []
        last_marked_done: List[str] = []
        last_reply_language: Optional[str] = None
        last_assistant_text: str = ""
        last_assistant_bubbles: List[str] = []

        if http_base_url and not session_token:
            failures.append("missing_session_token_for_http_mode")
            ok = False
            tw.write_summary(
                {
                    "run_id": tw.run_id,
                    "scenario_id": sc.scenario_id,
                    "ok": ok,
                    "failures": failures,
                    "duration_ms": int((time.time() - start) * 1000),
                }
            )
            tw.finalize_outcome(passed=ok)
            results.append(
                {
                    "scenario_id": sc.scenario_id,
                    "ok": ok,
                    "failures": failures,
                    "run_id": tw.run_id,
                    "run_dir": str(tw.run_dir),
                }
            )
            continue

        client_kwargs: Dict[str, Any] = {}
        if http_base_url:
            client_kwargs = {"base_url": http_base_url}
        else:
            client_kwargs = {"app": app, "base_url": "http://test"}

        async with httpx.AsyncClient(**client_kwargs) as client:
            for turn_idx in range(max_turns):
                tw.write_event({"type": "turn_user", "turn_idx": turn_idx, "text": redact_for_trace(user_msg)})

                if use_stream_endpoint:
                    out = await run_backend_inprocess_stream_turn(
                        client=client,
                        token=token,
                        user_message=user_msg,
                        assignments=sc.assignments,
                        do_reset=(turn_idx == 0),
                        user_id=user_id,
                    )
                else:
                    out = await run_backend_inprocess_turn(
                        client=client,
                        token=token,
                        user_message=user_msg,
                        assignments=sc.assignments,
                        do_reset=(turn_idx == 0),
                        user_id=user_id,
                    )

                tw.write_event(
                    {
                        "type": "turn_backend",
                        "turn_idx": turn_idx,
                        "assistant_text": redact_for_trace(out.assistant_text),
                        "assistant_bubbles": [redact_for_trace(t, max_chars=1000) for t in out.assistant_bubbles],
                        "selected_assignment_id": out.selected_assignment_id,
                        "marked_done_assignment_ids": out.marked_done_assignment_ids,
                        "raw_response": redact_for_trace(json.dumps(out.raw_response_json, ensure_ascii=False), max_chars=6000),
                    }
                )

                if out.selected_assignment_id:
                    selected_any = True
                    last_selected = out.selected_assignment_id
                selected_by_turn[turn_idx] = out.selected_assignment_id
                last_marked_done = out.marked_done_assignment_ids
                mark_done_by_turn[turn_idx] = list(out.marked_done_assignment_ids)
                last_assistant_text = out.assistant_text
                last_assistant_bubbles = list(out.assistant_bubbles)
                assistant_text_by_turn[turn_idx] = last_assistant_text
                last_reply_language = _detect_lang_hint(out.assistant_text)
                reply_language_by_turn[turn_idx] = last_reply_language

                # Next user message
                if script:
                    user_msg = script.pop(0)
                    continue
                break

        # Expectations (scenario-level)
        if sc.expected.require_any_selection and not selected_any:
            failures.append("expected_selection_missing")
        if sc.expected.require_no_selection and selected_any:
            failures.append("expected_no_selection_but_got_selection")
        if sc.expected.expected_selected_assignment_id:
            turn = sc.expected.expected_selected_assignment_id_turn
            if isinstance(turn, int):
                got = selected_by_turn.get(turn)
                if got != sc.expected.expected_selected_assignment_id:
                    failures.append("expected_selected_assignment_id_mismatch")
            elif last_selected != sc.expected.expected_selected_assignment_id:
                failures.append("expected_selected_assignment_id_mismatch")
        if sc.expected.forbidden_selected_assignment_ids:
            forbidden = set(sc.expected.forbidden_selected_assignment_ids)
            for sid in selected_by_turn.values():
                if sid and sid in forbidden:
                    failures.append("selected_assignment_id_forbidden")
                    break
        if sc.expected.expected_mark_done_assignment_id:
            turn = sc.expected.expected_mark_done_assignment_id_turn
            if isinstance(turn, int):
                got = mark_done_by_turn.get(turn, [])
                if sc.expected.expected_mark_done_assignment_id not in set(got):
                    failures.append("expected_mark_done_assignment_id_mismatch")
            elif sc.expected.expected_mark_done_assignment_id not in set(last_marked_done):
                failures.append("expected_mark_done_assignment_id_mismatch")
        if sc.expected.expected_reply_language and last_reply_language != sc.expected.expected_reply_language:
            failures.append("expected_reply_language_mismatch")
        if sc.expected.assistant_text_must_contain:
            for s in sc.expected.assistant_text_must_contain:
                if s and s not in last_assistant_text:
                    failures.append("assistant_text_missing_expected_substring")
                    break
        if sc.expected.assistant_text_forbidden_substrings:
            for s in sc.expected.assistant_text_forbidden_substrings:
                if s and s in last_assistant_text:
                    failures.append("assistant_text_contains_forbidden_substring")
                    break
        if sc.expected.max_question_marks is not None:
            qm = last_assistant_text.count("?")
            if qm > int(sc.expected.max_question_marks):
                failures.append("assistant_text_too_many_questions")
        if sc.expected.min_stream_message_count is not None:
            if len(last_assistant_bubbles) < int(sc.expected.min_stream_message_count):
                failures.append("stream_message_count_below_minimum")
        if sc.expected.expected_stream_message_count is not None:
            if len(last_assistant_bubbles) != int(sc.expected.expected_stream_message_count):
                failures.append("stream_message_count_mismatch")
        if sc.expected.stream_bubbles_must_contain:
            for s in sc.expected.stream_bubbles_must_contain:
                if s and not any(s in bubble for bubble in last_assistant_bubbles):
                    failures.append("stream_bubbles_missing_expected_substring")
                    break
        if sc.expected.first_stream_bubble_must_contain:
            first_bubble = last_assistant_bubbles[0] if last_assistant_bubbles else ""
            if sc.expected.first_stream_bubble_must_contain not in first_bubble:
                failures.append("first_stream_bubble_missing_expected_substring")
        if sc.expected.max_first_stream_bubble_chars is not None:
            first_bubble = last_assistant_bubbles[0] if last_assistant_bubbles else ""
            if len(first_bubble) > int(sc.expected.max_first_stream_bubble_chars):
                failures.append("first_stream_bubble_too_long")

        ok = len(failures) == 0
        tw.write_summary(
            {
                "run_id": tw.run_id,
                "scenario_id": sc.scenario_id,
                "ok": ok,
                "failures": failures,
                "duration_ms": int((time.time() - start) * 1000),
            }
        )
        tw.finalize_outcome(passed=ok)
        results.append(
            {
                "scenario_id": sc.scenario_id,
                "ok": ok,
                "failures": failures,
                "run_id": tw.run_id,
                "run_dir": str(tw.run_dir),
            }
        )

    return {"results": results, "aggregate": aggregate_suite(results)}


def main() -> None:
    out = asyncio.run(run_backend_integration_suite())
    print(json.dumps(out["aggregate"], ensure_ascii=False))


