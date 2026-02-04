from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


def _utc_date() -> str:
    return datetime.utcnow().date().isoformat()


@dataclass
class TraceWriter:
    root_dir: Path
    run_id: str
    run_dir: Path
    trace_path: Path

    @classmethod
    def create(cls, *, output_dir: str) -> "TraceWriter":
        run_id = uuid4().hex[:12]
        root = Path(output_dir)
        run_dir = root / _utc_date() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace_path = run_dir / "trace.jsonl"
        return cls(root_dir=root, run_id=run_id, run_dir=run_dir, trace_path=trace_path)

    def write_event(self, event: Dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        self.trace_path.open("a", encoding="utf-8").write(line + "\n")

    def write_summary(self, summary: Dict[str, Any]) -> None:
        path = self.run_dir / "summary.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def redact_for_trace(text: Optional[str], *, max_chars: int = 4000) -> Optional[str]:
    if text is None:
        return None
    t = str(text)
    if len(t) <= max_chars:
        return t
    return t[:max_chars] + "…"


