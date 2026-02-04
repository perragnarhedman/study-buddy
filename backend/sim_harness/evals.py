from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class HardCheckResult:
    ok: bool
    failures: List[str]


def hard_checks(
    *,
    selected_assignment_id: Optional[str],
    candidate_ids: List[str],
    assistant_text: str,
    require_any_selection: bool,
    require_no_selection: bool,
) -> HardCheckResult:
    failures: List[str] = []

    if not isinstance(assistant_text, str) or not assistant_text.strip():
        failures.append("assistant_text_empty")

    if selected_assignment_id is not None and selected_assignment_id not in candidate_ids:
        failures.append("selected_assignment_id_not_in_candidates")

    if require_any_selection and not selected_assignment_id:
        failures.append("expected_selection_missing")

    if require_no_selection and selected_assignment_id:
        failures.append("expected_no_selection_but_got_selection")

    return HardCheckResult(ok=(len(failures) == 0), failures=failures)


def aggregate_suite(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("ok") is True)
    return {"total": total, "passed": passed, "failed": total - passed}


