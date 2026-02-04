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

    candidates = build_candidates(scenario.assignments)
    candidate_ids = [str(c["id"]) for c in candidates if isinstance(c.get("id"), str)]

    conversation_history: List[Dict[str, str]] = []
    conversation_summary = ""  # harness-level; we keep empty for now
    user_state_json = "{}"

    state = StudentState()
    user_msg = scenario.initial_user_message

    selected_any = False
    failures: List[str] = []

    for turn_idx in range(config.max_turns):
        conversation_history.append({"role": "user", "text": user_msg})

        tw.write_event(
            {
                "type": "turn_user",
                "turn_idx": turn_idx,
                "text": redact_for_trace(user_msg),
            }
        )

        # Coach step with retries (be-sim.13)
        attempt = 0
        last_err: Optional[str] = None
        out = None
        while attempt <= config.max_retries:
            try:
                if config.use_openai_coach:
                    out = await run_coach_openai(
                        user_message=user_msg,
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
        nxt = next_user_message(lang=scenario.language, state=state, coach_selected_assignment_id=selected)
        if not nxt:
            break
        user_msg = nxt

    # Scenario-level expectations
    if scenario.expected.require_any_selection and not selected_any:
        failures.append("expected_selection_missing")
    if scenario.expected.require_no_selection and selected_any:
        failures.append("expected_no_selection_but_got_selection")

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


