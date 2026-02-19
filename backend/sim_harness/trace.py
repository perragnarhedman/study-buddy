from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


def _utc_date() -> str:
    return datetime.utcnow().date().isoformat()


def _safe_path_prefix(value: str) -> str:
    # Keep folder names readable and shell-friendly.
    cleaned = "".join(ch if (ch.isalnum() or ch in ("-", "_", ".")) else "_" for ch in value.strip())
    return cleaned.strip("._-") or "scenario"


@dataclass
class TraceWriter:
    root_dir: Path
    run_id: str
    run_dir: Path
    trace_path: Path

    @classmethod
    def create(cls, *, output_dir: str, scenario_id: Optional[str] = None) -> "TraceWriter":
        run_id = uuid4().hex[:12]
        root = Path(output_dir)
        dir_name = run_id
        if scenario_id:
            dir_name = f"{_safe_path_prefix(scenario_id)}_{run_id}"
        run_dir = root / _utc_date() / dir_name
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_path = run_dir / "trace.jsonl"
        return cls(root_dir=root, run_id=run_id, run_dir=run_dir, trace_path=trace_path)

    def write_event(self, event: Dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        self.trace_path.open("a", encoding="utf-8").write(line + "\n")

    def write_summary(self, summary: Dict[str, Any]) -> None:
        path = self.run_dir / "summary.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def finalize_outcome(self, *, passed: bool) -> None:
        """
        Rename run folder to include outcome after scenario prefix:
        <scenario_id>_<pass|fail>_<run_id>
        """
        run_name = self.run_dir.name
        suffix = f"_{self.run_id}"
        if not run_name.endswith(suffix):
            return
        scenario_prefix = run_name[: -len(suffix)]
        if not scenario_prefix:
            return

        outcome = "pass" if passed else "fail"
        target_name = f"{scenario_prefix}_{outcome}_{self.run_id}"
        target_dir = self.run_dir.parent / target_name
        if target_dir == self.run_dir:
            return
        self.run_dir.rename(target_dir)
        self.run_dir = target_dir
        self.trace_path = self.run_dir / "trace.jsonl"


def redact_for_trace(text: Optional[str], *, max_chars: int = 4000) -> Optional[str]:
    if text is None:
        return None
    t = str(text)
    if len(t) <= max_chars:
        return t
    return t[:max_chars] + "…"


