from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ValidationError

from sim_harness.evals import aggregate_suite, hard_checks
from sim_harness.models import RunConfig, Scenario
from sim_harness.student import StudentState, next_user_message
from sim_harness.sut import build_candidates, run_coach_mock, run_coach_openai
from sim_harness.trace import TraceWriter, redact_for_trace


@dataclass
class RunResult:
    scenario_id: str
    ok: bool
    failures: List[str]
    run_id: str
    run_dir: str


def _history_lines(history: List[Dict[str, str]]) -> str:
    return "\n".join([f"{h['role']}: {h['text']}" for h in history])

def _is_ack(text: str) -> bool:
    ut = (text or "").strip().lower().strip(".!?")
    return ut in {"ja", "japp", "ok", "okej", "yes", "yep", "sure", "kör", "bra", "okay"}


async def run_scenario(*, scenario: Scenario, config: RunConfig) -> RunResult:
    tw = TraceWriter.create(output_dir=config.output_dir)
    start = time.time()

    tw.write_event(
        {
            "type": "run_start",
            "run_id": tw.run_id,
            "scenario_id": scenario.scenario_id,
            "run_config": config.model_dump(),
            "scenario_title": scenario.title,
        }
    )

    base_candidates = build_candidates(scenario.assignments)

    conversation_history: List[Dict[str, str]] = []
    conversation_summary = ""  # harness-level; we keep empty for now
    user_state_obj: Dict[str, Any] = {}
    user_state_json = "{}"

    state = StudentState()
    script = list(scenario.user_messages or [])
    if not script:
        user_msg = scenario.initial_user_message
    else:
        user_msg = script.pop(0)

    selected_any = False
    failures: List[str] = []
    selected_by_turn: Dict[int, Optional[str]] = {}
    mark_done_by_turn: Dict[int, Optional[str]] = {}
    assistant_text_by_turn: Dict[int, str] = {}
    reply_language_by_turn: Dict[int, Optional[str]] = {}
    last_selected: Optional[str] = None
    last_mark_done: Optional[str] = None
    last_reply_language: Optional[str] = None
    last_assistant_text: str = ""

    for turn_idx in range(config.max_turns):
        conversation_history.append({"role": "user", "text": user_msg})

        tw.write_event(
            {
                "type": "turn_user",
                "turn_idx": turn_idx,
                "text": redact_for_trace(user_msg),
            }
        )

        # Build per-turn candidates + user_state (simulate server persistence).
        candidates: List[Dict[str, Any]] = []
        for c in base_candidates:
            cc = dict(c)
            cc["is_last_selected"] = bool(last_selected and cc.get("id") == last_selected)
            candidates.append(cc)
        if last_selected:
            user_state_obj["last_selected_assignment_id"] = last_selected
        user_state_json = json.dumps(user_state_obj, ensure_ascii=False)

        # If the student acknowledges, restrict to last-selected to keep the thread coherent.
        ack = _is_ack(user_msg)
        if ack and last_selected:
            candidates = [c for c in candidates if c.get("id") == last_selected] or candidates

        candidate_ids = [str(c["id"]) for c in candidates if isinstance(c.get("id"), str)]

        # Coach step with retries (be-sim.13)
        attempt = 0
        last_err: Optional[str] = None
        out = None
        while attempt <= config.max_retries:
            try:
                if config.use_openai_coach:
                    msg_for_model = user_msg
                    if ack and last_selected:
                        msg_for_model = (
                            f"{msg_for_model}\n\nNOTE: The student is acknowledging your previous suggestion. "
                            "Continue the same task/thread; do not switch subjects."
                        )
                    out = await run_coach_openai(
                        user_message=msg_for_model,
                        candidates=candidates,
                        conversation_history=_history_lines(conversation_history[:-1]),
                        conversation_summary=conversation_summary,
                        user_state_json=user_state_json,
                    )
                else:
                    out = run_coach_mock(user_message=user_msg, candidates=candidates, lang=scenario.language)
                break
            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_err = type(e).__name__
            except Exception as e:
                # Retry only for clearly transient OpenAI/network-ish failures.
                last_err = type(e).__name__
                msg = str(e)
                if "OpenAI" in msg or "timeout" in msg.lower() or "unavailable" in msg.lower():
                    pass
                else:
                    # Treat schema/validation errors as non-retry by default.
                    break
            attempt += 1

        if out is None:
            failures.append(f"coach_failed:{last_err or 'unknown'}")
            break

        decision = out.decision
        selected = out.selected_assignment_id
        if selected:
            selected_any = True
        if selected:
            last_selected = selected
        last_mark_done = getattr(decision, "mark_done_assignment_id", None)
        last_reply_language = getattr(decision, "reply_language", None)
        last_assistant_text = getattr(decision, "assistant_text", "") or ""
        selected_by_turn[turn_idx] = selected
        mark_done_by_turn[turn_idx] = last_mark_done
        assistant_text_by_turn[turn_idx] = last_assistant_text
        reply_language_by_turn[turn_idx] = last_reply_language

        tw.write_event(
            {
                "type": "turn_coach",
                "turn_idx": turn_idx,
                "assistant_text": redact_for_trace(getattr(decision, "assistant_text", "")),
                "selected_assignment_id": selected,
                "reply_language": getattr(decision, "reply_language", None),
                "attempts": attempt + 1,
                "prompt": redact_for_trace(out.prompt, max_chars=6000),
                "raw_model_output": redact_for_trace(out.raw_model_output, max_chars=6000),
            }
        )

        conversation_history.append({"role": "assistant", "text": getattr(decision, "assistant_text", "")})

        # Hard checks per turn.
        hc = hard_checks(
            selected_assignment_id=selected,
            candidate_ids=candidate_ids,
            assistant_text=getattr(decision, "assistant_text", ""),
            require_any_selection=False,
            require_no_selection=False,
        )
        if not hc.ok:
            failures.extend(hc.failures)

        # Student step
        if script:
            nxt = script.pop(0)
        else:
            nxt = next_user_message(lang=scenario.language, state=state, coach_selected_assignment_id=selected)
        if not nxt:
            break
        user_msg = nxt

    # Scenario-level expectations
    if config.enforce_expected:
        if scenario.expected.require_any_selection and not selected_any:
            failures.append("expected_selection_missing")
        if scenario.expected.require_no_selection and selected_any:
            failures.append("expected_no_selection_but_got_selection")
        if scenario.expected.expected_selected_assignment_id:
            turn = scenario.expected.expected_selected_assignment_id_turn
            if isinstance(turn, int):
                got = selected_by_turn.get(turn)
                if got != scenario.expected.expected_selected_assignment_id:
                    failures.append("expected_selected_assignment_id_mismatch")
            else:
                if last_selected != scenario.expected.expected_selected_assignment_id:
                    failures.append("expected_selected_assignment_id_mismatch")
        if scenario.expected.forbidden_selected_assignment_ids:
            forbidden = set(scenario.expected.forbidden_selected_assignment_ids)
            for t, sid in selected_by_turn.items():
                if sid and sid in forbidden:
                    failures.append("selected_assignment_id_forbidden")
                    break
        if scenario.expected.expected_mark_done_assignment_id and last_mark_done != scenario.expected.expected_mark_done_assignment_id:
            failures.append("expected_mark_done_assignment_id_mismatch")
        if scenario.expected.expected_reply_language and last_reply_language != scenario.expected.expected_reply_language:
            failures.append("expected_reply_language_mismatch")
        if scenario.expected.assistant_text_must_contain:
            for s in scenario.expected.assistant_text_must_contain:
                if s and s not in last_assistant_text:
                    failures.append("assistant_text_missing_expected_substring")
                    break
        if getattr(scenario.expected, "assistant_text_forbidden_substrings", None):
            for s in scenario.expected.assistant_text_forbidden_substrings:
                if s and s in last_assistant_text:
                    failures.append("assistant_text_contains_forbidden_substring")
                    break
        if scenario.expected.max_question_marks is not None:
            qm = last_assistant_text.count("?")
            if qm > int(scenario.expected.max_question_marks):
                failures.append("assistant_text_too_many_questions")

    ok = len(failures) == 0
    tw.write_summary(
        {
            "run_id": tw.run_id,
            "scenario_id": scenario.scenario_id,
            "ok": ok,
            "failures": failures,
            "duration_ms": int((time.time() - start) * 1000),
        }
    )
    return RunResult(
        scenario_id=scenario.scenario_id,
        ok=ok,
        failures=failures,
        run_id=tw.run_id,
        run_dir=str(tw.run_dir),
    )


async def run_suite(*, scenarios: List[Scenario], config: RunConfig) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for sc in scenarios:
        rr = await run_scenario(scenario=sc, config=config)
        results.append(
            {
                "scenario_id": rr.scenario_id,
                "ok": rr.ok,
                "failures": rr.failures,
                "run_id": rr.run_id,
                "run_dir": rr.run_dir,
            }
        )
    return {"results": results, "aggregate": aggregate_suite(results)}


