from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.db import get_tokens, upsert_tokens
from app.models.schemas import Assignment


GOOGLE_API_BASE = "https://classroom.googleapis.com/v1"


async def fetch_classroom_assignments(user_id: str) -> list[Assignment]:
    tok = get_tokens(user_id)
    if not tok:
        raise PermissionError("no_tokens")

    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    expires_at = tok.get("expires_at")

    if not access_token:
        raise PermissionError("no_access_token")

    # Refresh if expired or near-expired.
    if expires_at and int(expires_at) <= int(time.time()) + 60:
        if not refresh_token:
            raise PermissionError("no_refresh_token")
        access_token = await _refresh_access_token(user_id, refresh_token)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            courses = await _list_courses(client, access_token)
            out: list[Assignment] = []
            for c in courses:
                course_id = c.get("id")
                course_name = c.get("name") or "Course"
                if not course_id:
                    continue
                course_work = await _list_coursework(client, access_token, course_id)
                out.extend(_normalize_coursework(course_work, course_name))
            return out
    except httpx.RequestError:
        raise ConnectionError("google_unreachable")


async def _refresh_access_token(user_id: str, refresh_token: str) -> str:
    settings = get_settings()
    if not settings.google_client_id:
        raise PermissionError("oauth_not_configured")

    payload = {
        "client_id": settings.google_client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if settings.google_client_secret:
        payload["client_secret"] = settings.google_client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data=payload)
        if r.status_code != 200:
            raise PermissionError("refresh_failed")
        tok = r.json()
        access_token = tok.get("access_token")
        expires_in = tok.get("expires_in")
        token_type = tok.get("token_type")
        scope = tok.get("scope")
        if not access_token:
            raise PermissionError("refresh_failed")

    expires_at = int(time.time() + int(expires_in)) if expires_in else None
    upsert_tokens(
        user_id=user_id,
        access_token=access_token,
        refresh_token=None,  # keep existing
        expires_at=expires_at,
        token_type=token_type,
        scope=scope,
        id_token=None,
    )
    return access_token


async def _list_courses(client: httpx.AsyncClient, access_token: str) -> list[dict]:
    r = await client.get(
        f"{GOOGLE_API_BASE}/courses",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"courseStates": "ACTIVE"},
    )
    if r.status_code == 401:
        raise PermissionError("google_unauthorized")
    r.raise_for_status()
    data = r.json()
    return data.get("courses", []) or []


async def _list_coursework(client: httpx.AsyncClient, access_token: str, course_id: str) -> list[dict]:
    r = await client.get(
        f"{GOOGLE_API_BASE}/courses/{course_id}/courseWork",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"orderBy": "dueDate desc"},
    )
    if r.status_code == 401:
        raise PermissionError("google_unauthorized")
    # Some classes may have no coursework; Google returns 404 sometimes.
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data.get("courseWork", []) or []


def _normalize_coursework(coursework: list[dict], course_name: str) -> list[Assignment]:
    out: list[Assignment] = []
    for w in coursework:
        wid = w.get("id") or ""
        title = w.get("title") or "Assignment"
        due_iso = _due_iso(w.get("dueDate"), w.get("dueTime"))
        desc = w.get("description")
        url = w.get("alternateLink")
        # Classroom doesn't provide estimated duration; leave None.
        out.append(
            Assignment(
                id=str(wid),
                title=str(title),
                dueDate=due_iso,
                courseName=course_name,
                description=str(desc) if isinstance(desc, str) else None,
                url=str(url) if isinstance(url, str) else None,
                estimatedMinutes=None,
            )
        )
    return out


def _due_iso(due_date: Optional[dict], due_time: Optional[dict]) -> Optional[str]:
    if not isinstance(due_date, dict):
        return None
    y = due_date.get("year")
    m = due_date.get("month")
    d = due_date.get("day")
    if not (isinstance(y, int) and isinstance(m, int) and isinstance(d, int)):
        return None
    hh = 0
    mm = 0
    if isinstance(due_time, dict):
        hh = int(due_time.get("hours") or 0)
        mm = int(due_time.get("minutes") or 0)
    dt = datetime(y, m, d, hh, mm, tzinfo=timezone.utc)
    return dt.isoformat()


