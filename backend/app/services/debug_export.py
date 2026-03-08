from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings


@dataclass(frozen=True)
class DebugExportResult:
    wrote: bool
    path: str | None


def _hash_user_id(user_id: str) -> str:
    return sha256(user_id.encode("utf-8")).hexdigest()[:12]


def export_chat_trace(*, user_id: str, payload: dict) -> DebugExportResult:
    """
    Write a single JSON trace per chat request for offline analysis.
    Partitioned by UTC date: <debug_export_dir>/YYYY-MM-DD/<timestamp>_<userhash>_<id>.json
    """
    settings = get_settings()
    if not settings.debug_export_enabled:
        return DebugExportResult(wrote=False, path=None)

    base = Path(settings.debug_export_dir)
    now = datetime.now(timezone.utc)
    date_part = now.date().isoformat()
    out_dir = base / date_part
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = now.strftime("%H%M%S.%f")[:-3]  # milliseconds
    user_hash = _hash_user_id(user_id)
    rid = uuid4().hex[:8]
    fname = f"{ts}_{user_hash}_{rid}.json"

    full_payload = {
        "type": "chat_trace",
        "schema_version": 2,
        "created_at": now.isoformat(),
        "user_hash": user_hash,
        **payload,
    }

    tmp_path = out_dir / f".{fname}.tmp"
    final_path = out_dir / fname
    tmp_path.write_text(json.dumps(full_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, final_path)
    return DebugExportResult(wrote=True, path=str(final_path))


