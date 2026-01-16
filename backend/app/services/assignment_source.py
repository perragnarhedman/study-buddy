from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

from app.models.schemas import Assignment
from app.services.classroom import fetch_classroom_assignments
from app.services.planner import stub_assignments


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "assignments.json"


async def select_assignments(user_id: Optional[str]) -> Tuple[list[Assignment], dict]:
    # Explicit fallback chain:
    # 1) Authenticated + classroom succeeds
    # 2) Local fixture exists
    # 3) Hardcoded stub list (3)
    if user_id:
        try:
            assignments = await fetch_classroom_assignments(user_id)
            if not assignments:
                raise RuntimeError("classroom_empty")
            print("assignments_source used_classroom=true used_fixture=false fallback_reason=none")
            return assignments, {"used_classroom": True, "used_fixture": False}
        except Exception:
            print("assignments_source used_classroom=false used_fixture=false fallback_reason=classroom_failed")

    if FIXTURE_PATH.exists():
        try:
            raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            assignments = [Assignment.model_validate(a) for a in raw]
            print("assignments_source used_classroom=false used_fixture=true fallback_reason=none")
            return assignments, {"used_classroom": False, "used_fixture": True}
        except Exception:
            print("assignments_source used_classroom=false used_fixture=false fallback_reason=fixture_invalid")

    print("assignments_source used_classroom=false used_fixture=false fallback_reason=using_stub")
    return stub_assignments(), {"used_classroom": False, "used_fixture": False}


