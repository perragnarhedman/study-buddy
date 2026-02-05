from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import ValidationError

from sim_harness.models import Scenario


SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"

_SUITE_DIR = {
    "quick": "golden",
    "extended": "extended",
    "integration": "integration",
}


def load_scenarios(*, suite: str = "quick") -> List[Scenario]:
    """
    Load scenarios from disk. For now:
    - quick: 3 golden scenarios (deterministic bring-up)
    - extended: additional scenarios for broader coverage
    - integration: scenarios that run against the real backend /chat/send persistence path
    """
    if suite not in _SUITE_DIR:
        raise ValueError(f"unknown_suite:{suite}")
    d = SCENARIOS_DIR / _SUITE_DIR[suite]
    paths = sorted(d.glob("*.json"))
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


