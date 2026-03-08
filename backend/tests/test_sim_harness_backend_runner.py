import asyncio

from sim_harness.backend_runner import _detect_lang_hint, run_backend_integration_suite


def test_backend_runner_detect_lang_hint_supports_swedish_characters() -> None:
    assert _detect_lang_hint("Hej, vad har jag kvar?") == "sv"
    assert _detect_lang_hint("Help me choose") == "en"
    assert _detect_lang_hint("") is None


def test_backend_llm_suite_loads() -> None:
    from sim_harness.scenarios import load_scenarios

    scenarios = load_scenarios(suite="backend_llm")
    assert len(scenarios) >= 3


def test_backend_stream_suite_loads() -> None:
    from sim_harness.scenarios import load_scenarios

    scenarios = load_scenarios(suite="backend_stream")
    assert len(scenarios) >= 3


def test_backend_runner_enforces_text_expectations(monkeypatch, tmp_path) -> None:
    import sim_harness.backend_runner as backend_runner
    from sim_harness.backend_sut import BackendTurnResult

    async def fake_install():
        return None

    async def fake_turn(**kwargs):
        return BackendTurnResult(
            assistant_text="Which page should I do tomorrow?",
            assistant_bubbles=["Which page should I do tomorrow?"],
            selected_assignment_id="a1",
            marked_done_assignment_ids=[],
            raw_response_json={
                "assistant_message": {"text": "Which page should I do tomorrow?"},
                "best_next_action": {"sourceAssignmentId": "a1"},
            },
        )

    monkeypatch.setattr(backend_runner, "_install_deterministic_coach", fake_install)
    monkeypatch.setattr(backend_runner, "run_backend_inprocess_turn", fake_turn)
    monkeypatch.setattr(backend_runner, "prepare_backend_env", lambda **kwargs: ("db", tmp_path / "fixture.json"))

    out = asyncio.run(
        run_backend_integration_suite(
            suite="backend_llm",
            output_dir=str(tmp_path / "sim_runs"),
            max_turns=1,
            use_openai_coach=False,
            http_base_url="http://example.test",
            session_token="token",
        )
    )
    assert out["aggregate"]["failed"] >= 1
    failures = out["results"][0]["failures"]
    assert any(
        failure in failures
        for failure in [
            "assistant_text_missing_expected_substring",
            "assistant_text_contains_forbidden_substring",
            "expected_reply_language_mismatch",
        ]
    )


def test_backend_runner_enforces_stream_bubble_expectations(monkeypatch, tmp_path) -> None:
    import sim_harness.backend_runner as backend_runner
    from sim_harness.backend_sut import BackendTurnResult

    async def fake_install():
        return None

    async def fake_stream_turn(**kwargs):
        return BackendTurnResult(
            assistant_text="Only one bubble",
            assistant_bubbles=["Only one bubble"],
            selected_assignment_id=None,
            marked_done_assignment_ids=[],
            raw_response_json={"events": [{"type": "message_completed"}]},
        )

    monkeypatch.setattr(backend_runner, "_install_deterministic_coach", fake_install)
    monkeypatch.setattr(backend_runner, "run_backend_inprocess_stream_turn", fake_stream_turn)
    monkeypatch.setattr(backend_runner, "prepare_backend_env", lambda **kwargs: ("db", tmp_path / "fixture.json"))

    out = asyncio.run(
        run_backend_integration_suite(
            suite="backend_stream",
            output_dir=str(tmp_path / "sim_runs"),
            max_turns=1,
            use_openai_coach=False,
            http_base_url="http://example.test",
            session_token="token",
        )
    )
    assert out["aggregate"]["failed"] >= 1
    failures = out["results"][0]["failures"]
    assert "stream_message_count_below_minimum" in failures


def test_backend_runner_enforces_first_stream_bubble_expectations(monkeypatch, tmp_path) -> None:
    import sim_harness.backend_runner as backend_runner
    from sim_harness.backend_sut import BackendTurnResult

    async def fake_install():
        return None

    async def fake_stream_turn(**kwargs):
        return BackendTurnResult(
            assistant_text="Long opener bubble\n\nMath next",
            assistant_bubbles=["Hello there, here is your overview", "Math next"],
            selected_assignment_id=None,
            marked_done_assignment_ids=[],
            raw_response_json={"events": [{"type": "message_completed"}]},
        )

    monkeypatch.setattr(backend_runner, "_install_deterministic_coach", fake_install)
    monkeypatch.setattr(backend_runner, "run_backend_inprocess_stream_turn", fake_stream_turn)
    monkeypatch.setattr(backend_runner, "prepare_backend_env", lambda **kwargs: ("db", tmp_path / "fixture.json"))

    out = asyncio.run(
        run_backend_integration_suite(
            suite="backend_stream",
            output_dir=str(tmp_path / "sim_runs"),
            max_turns=1,
            use_openai_coach=False,
            http_base_url="http://example.test",
            session_token="token",
        )
    )
    assert out["aggregate"]["failed"] >= 1
    result = next(r for r in out["results"] if r["scenario_id"] == "bstream-004")
    failures = result["failures"]
    assert "first_stream_bubble_missing_expected_substring" in failures or "first_stream_bubble_too_long" in failures
