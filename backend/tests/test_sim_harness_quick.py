import asyncio

from app.models.agent import CoachDecision
from sim_harness.models import RunConfig, Scenario
from sim_harness.orchestrator import run_suite
from sim_harness.scenarios import load_scenarios
from sim_harness.sut import SUTOutput


def test_sim_harness_quick_suite_is_deterministic(tmp_path) -> None:
    scenarios = load_scenarios(suite="quick")
    assert len(scenarios) == 3

    cfg = RunConfig(
        suite="quick",
        max_turns=8,
        max_retries=1,
        use_openai_coach=False,
        use_openai_judge=False,
        output_dir=str(tmp_path / "sim_runs"),
    )
    out = asyncio.run(run_suite(scenarios=scenarios, config=cfg))
    assert out["aggregate"]["total"] == 3
    assert out["aggregate"]["failed"] == 0


def test_sim_harness_extended_scenarios_load() -> None:
    scenarios = load_scenarios(suite="extended")
    assert len(scenarios) >= 10


def test_sim_harness_integration_suite_loads() -> None:
    scenarios = load_scenarios(suite="integration")
    assert len(scenarios) >= 3


def test_sim_harness_backend_llm_suite_loads() -> None:
    scenarios = load_scenarios(suite="backend_llm")
    assert len(scenarios) >= 3


def test_sim_harness_backend_stream_suite_loads() -> None:
    scenarios = load_scenarios(suite="backend_stream")
    assert len(scenarios) >= 3


def test_sim_harness_extended_suite_runs_in_mock_mode_without_enforcing_expectations(tmp_path) -> None:
    scenarios = load_scenarios(suite="extended")
    cfg = RunConfig(
        suite="extended",
        max_turns=8,
        max_retries=1,
        use_openai_coach=False,
        use_openai_judge=False,
        enforce_expected=False,
        output_dir=str(tmp_path / "sim_runs"),
    )
    out = asyncio.run(run_suite(scenarios=scenarios, config=cfg))
    assert out["aggregate"]["total"] >= 10


def test_mark_done_expected_turn_uses_configured_turn(tmp_path, monkeypatch) -> None:
    call_count = {"n": 0}

    def fake_run_coach_mock(*, user_message: str, candidates, lang: str) -> SUTOutput:
        call_count["n"] += 1
        mark_done = "a-eng" if call_count["n"] == 1 else None
        decision = CoachDecision.model_validate(
            {
                "assistant_text": "OK.",
                "selected_assignment_id": "a-math",
                "mark_done_assignment_id": mark_done,
                "selected_plan_item_id": None,
                "mark_done_plan_item_id": None,
                "reply_language": "en",
            }
        )
        return SUTOutput(
            decision=decision,
            raw_model_output="{}",
            prompt="(test)",
            selected_assignment_id=decision.selected_assignment_id,
        )

    monkeypatch.setattr("sim_harness.orchestrator.run_coach_mock", fake_run_coach_mock)

    scenario = Scenario.model_validate(
        {
            "scenario_id": "t-mark-done-turn",
            "title": "mark-done expectation can target a specific turn",
            "language": "en",
            "assignments": [
                {"id": "a-eng", "title": "English essay draft", "courseName": "English"},
                {"id": "a-math", "title": "Math worksheet", "courseName": "Math"},
            ],
            "initial_user_message": "I finished the English essay.",
            "user_messages": ["I finished the English essay.", "Ok."],
            "expected": {
                "expected_mark_done_assignment_id": "a-eng",
                "expected_mark_done_assignment_id_turn": 0,
            },
        }
    )

    cfg = RunConfig(
        suite="test",
        max_turns=2,
        max_retries=0,
        use_openai_coach=False,
        use_openai_judge=False,
        enforce_expected=True,
        output_dir=str(tmp_path / "sim_runs"),
    )

    out = asyncio.run(run_suite(scenarios=[scenario], config=cfg))
    assert out["aggregate"]["failed"] == 0

