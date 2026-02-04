import asyncio

from sim_harness.models import RunConfig
from sim_harness.orchestrator import run_suite
from sim_harness.scenarios import load_scenarios


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


