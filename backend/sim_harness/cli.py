from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sim_harness.models import RunConfig
from sim_harness.backend_runner import run_backend_integration_suite
from sim_harness.orchestrator import run_suite
from sim_harness.scenarios import load_scenarios


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sim-harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    quick = sub.add_parser("quick", help="Run the quick suite (3 golden scenarios)")
    quick.add_argument("--max-turns", type=int, default=8)
    quick.add_argument("--max-retries", type=int, default=1)
    quick.add_argument("--no-openai-coach", action="store_true")
    quick.add_argument("--output-dir", type=str, default="sim_runs")

    ext = sub.add_parser("extended", help="Run the extended suite (additional scenarios)")
    ext.add_argument("--max-turns", type=int, default=8)
    ext.add_argument("--max-retries", type=int, default=1)
    ext.add_argument("--no-openai-coach", action="store_true")
    ext.add_argument("--ignore-expected", action="store_true")
    ext.add_argument("--output-dir", type=str, default="sim_runs")

    backend = sub.add_parser("backend", help="Run the integration suite against real backend /chat/send (in-process)")
    backend.add_argument("--max-turns", type=int, default=6)
    backend.add_argument("--output-dir", type=str, default="sim_runs")
    backend.add_argument(
        "--suite",
        type=str,
        default="integration",
        choices=["integration", "backend_llm", "backend_stream"],
        help="Scenario suite for backend mode. Use backend_llm or backend_stream for conversational-rule checks with the real coach.",
    )
    backend.add_argument(
        "--use-openai-coach",
        action="store_true",
        help="Use real OpenAI coach (no patching). Requires OPENAI_API_KEY.",
    )
    backend.add_argument(
        "--http-base-url",
        type=str,
        default="",
        help="Call an external running backend instead of in-process (requires --session-token).",
    )
    backend.add_argument("--session-token", type=str, default="", help="Bearer token for --http-base-url mode.")

    return p


async def _run_quick(args: argparse.Namespace) -> int:
    cfg = RunConfig(
        suite="quick",
        max_turns=int(args.max_turns),
        max_retries=int(args.max_retries),
        use_openai_coach=(not args.no_openai_coach),
        output_dir=str(args.output_dir),
    )
    scenarios = load_scenarios(suite="quick")
    out = await run_suite(scenarios=scenarios, config=cfg)
    print(json.dumps(out["aggregate"], ensure_ascii=False))
    # Print failures for quick visibility.
    for r in out["results"]:
        if not r["ok"]:
            print(f"FAIL {r['scenario_id']}: {r['failures']} (run_dir={r['run_dir']})")
    return 0 if out["aggregate"]["failed"] == 0 else 1


async def _run_extended(args: argparse.Namespace) -> int:
    cfg = RunConfig(
        suite="extended",
        max_turns=int(args.max_turns),
        max_retries=int(args.max_retries),
        use_openai_coach=(not args.no_openai_coach),
        enforce_expected=(not args.ignore_expected),
        output_dir=str(args.output_dir),
    )
    scenarios = load_scenarios(suite="extended")
    out = await run_suite(scenarios=scenarios, config=cfg)
    print(json.dumps(out["aggregate"], ensure_ascii=False))
    for r in out["results"]:
        if not r["ok"]:
            print(f"FAIL {r['scenario_id']}: {r['failures']} (run_dir={r['run_dir']})")
    return 0 if out["aggregate"]["failed"] == 0 else 1


async def _run_backend(args: argparse.Namespace) -> int:
    out = await run_backend_integration_suite(
        suite=str(args.suite),
        output_dir=str(args.output_dir),
        max_turns=int(args.max_turns),
        use_openai_coach=bool(args.use_openai_coach),
        http_base_url=str(args.http_base_url or "") or None,
        session_token=str(args.session_token or "") or None,
    )
    print(json.dumps(out["aggregate"], ensure_ascii=False))
    for r in out["results"]:
        if not r["ok"]:
            print(f"FAIL {r['scenario_id']}: {r['failures']} (run_dir={r['run_dir']})")
    return 0 if out["aggregate"]["failed"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = _parser().parse_args(argv)
    if args.cmd == "quick":
        return asyncio.run(_run_quick(args))
    if args.cmd == "extended":
        return asyncio.run(_run_extended(args))
    if args.cmd == "backend":
        return asyncio.run(_run_backend(args))
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())


