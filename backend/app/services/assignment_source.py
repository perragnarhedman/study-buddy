from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

from app.models.schemas import Assignment
from app.core.config import get_settings
from app.services.classroom import fetch_classroom_assignments


_DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "assignments.json"
logger = logging.getLogger(__name__)
_CACHE_LOCK = asyncio.Lock()
_ASSIGNMENTS_CACHE: dict[str, tuple[float, list[Assignment], dict]] = {}


def _fixture_path() -> Path:
    # Read at runtime so test harnesses can override per run without relying on import timing.
    return Path(os.environ.get("ASSIGNMENTS_FIXTURE_PATH") or _DEFAULT_FIXTURE_PATH)


async def select_assignments(user_id: Optional[str]) -> Tuple[list[Assignment], dict]:
    # Explicit fallback chain:
    # 1) Authenticated + classroom succeeds
    # 2) Local fixture exists
    # 3) Hardcoded stub list (3)
    if user_id:
        cached = await _get_cached_assignments(user_id)
        if cached is not None:
            return cached
        try:
            assignments = await fetch_classroom_assignments(user_id)
            if not assignments:
                raise RuntimeError("classroom_empty")
            meta = {"used_classroom": True, "used_fixture": False}
            logger.info("assignments_source used_classroom=true used_fixture=false fallback_reason=none")
            await _set_cached_assignments(user_id, assignments, meta)
            return assignments, meta
        except (PermissionError, ConnectionError, RuntimeError):
            logger.warning("assignments_source used_classroom=false used_fixture=false fallback_reason=classroom_failed")

    fixture_path = _fixture_path()
    if fixture_path.exists():
        try:
            raw = json.loads(fixture_path.read_text(encoding="utf-8"))
            assignments = [Assignment.model_validate(a) for a in raw]
            logger.info("assignments_source used_classroom=false used_fixture=true fallback_reason=none")
            return assignments, {"used_classroom": False, "used_fixture": True}
        except (OSError, json.JSONDecodeError, ValueError):
            logger.warning("assignments_source used_classroom=false used_fixture=false fallback_reason=fixture_invalid")

    logger.info("assignments_source used_classroom=false used_fixture=false fallback_reason=using_stub")
    return stub_assignments(), {"used_classroom": False, "used_fixture": False}


def stub_assignments() -> list[Assignment]:
    # Deterministic local fallback if classroom+fixture sources are unavailable.
    from datetime import date

    def _days_from_today_iso(days: int) -> str:
        return (date.today()).fromordinal(date.today().toordinal() + days).isoformat()

    return [
        Assignment(
            id="a1",
            title="Math problem set 3",
            dueDate=_days_from_today_iso(2),
            courseName="Math",
            description=None,
            url=None,
            estimatedMinutes=60,
        ),
        Assignment(
            id="a2",
            title="History reading: Chapter 7 notes",
            dueDate=_days_from_today_iso(4),
            courseName="History",
            description=None,
            url=None,
            estimatedMinutes=30,
        ),
        Assignment(
            id="a3",
            title="English essay draft",
            dueDate=_days_from_today_iso(6),
            courseName="English",
            description=None,
            url=None,
            estimatedMinutes=90,
        ),
    ]


async def _get_cached_assignments(user_id: str) -> Optional[Tuple[list[Assignment], dict]]:
    ttl = max(int(get_settings().classroom_cache_ttl_seconds), 0)
    if ttl <= 0:
        return None
    now = time.monotonic()
    async with _CACHE_LOCK:
        item = _ASSIGNMENTS_CACHE.get(user_id)
        if not item:
            return None
        expires_at, assignments, meta = item
        if now >= expires_at:
            _ASSIGNMENTS_CACHE.pop(user_id, None)
            return None
        # Return copies to avoid mutation leaking across requests.
        return [a.model_copy(deep=True) for a in assignments], dict(meta)


async def _set_cached_assignments(user_id: str, assignments: list[Assignment], meta: dict) -> None:
    ttl = max(int(get_settings().classroom_cache_ttl_seconds), 0)
    if ttl <= 0:
        return
    cached = [a.model_copy(deep=True) for a in assignments]
    async with _CACHE_LOCK:
        _ASSIGNMENTS_CACHE[user_id] = (time.monotonic() + ttl, cached, dict(meta))


