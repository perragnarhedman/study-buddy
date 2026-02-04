from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sim_harness.models import RunConfig
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


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = _parser().parse_args(argv)
    if args.cmd == "quick":
        return asyncio.run(_run_quick(args))
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())


