from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import ValidationError

from sim_harness.models import Scenario


SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


def load_scenarios(*, suite: str = "quick") -> List[Scenario]:
    """
    Load scenarios from disk. For now:
    - quick: all golden scenarios (3)
    """
    if suite not in {"quick"}:
        raise ValueError(f"unknown_suite:{suite}")
    golden = SCENARIOS_DIR / "golden"
    paths = sorted(golden.glob("*.json"))
    if not paths:
        raise RuntimeError("no_scenarios_found")

    out: List[Scenario] = []
    for p in paths:
        raw = json.loads(p.read_text(encoding="utf-8"))
        try:
            out.append(Scenario.model_validate(raw))
        except ValidationError as e:
            raise ValueError(f"scenario_invalid:{p.name}:{e}") from e
    return out


