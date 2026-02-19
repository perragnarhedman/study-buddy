from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.db import get_tokens, upsert_tokens
from app.models.schemas import Assignment, AttachmentLink


GOOGLE_API_BASE = "https://classroom.googleapis.com/v1"
logger = logging.getLogger(__name__)


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
            settings = get_settings()
            max_concurrency = max(int(settings.classroom_max_concurrency), 1)
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _fetch_one_course(c: dict) -> list[Assignment]:
                course_id = c.get("id")
                course_name = c.get("name") or "Course"
                if not course_id:
                    return []
                async with semaphore:
                    try:
                        course_work = await _list_coursework(client, access_token, course_id)
                    except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError):
                        logger.warning("classroom_coursework_failed course_id=%s", course_id)
                        return []
                    return _normalize_coursework(course_work, str(course_name))

            per_course = await asyncio.gather(*[_fetch_one_course(c) for c in courses], return_exceptions=False)
            for rows in per_course:
                out.extend(rows)
            return out
    except httpx.RequestError:
        raise ConnectionError("google_unreachable")
    except httpx.HTTPStatusError:
        # Any other unexpected Google HTTP error should not crash the API.
        raise ConnectionError("google_http_error")


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
    if r.status_code in (401, 403):
        # Upstream auth/scopes/api access issues -> treat as upstream failure (502).
        raise ConnectionError(f"google_forbidden_{r.status_code}")
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
        raise ConnectionError("google_unauthorized")
    if r.status_code == 403:
        # Some courses may be inaccessible for coursework; skip rather than failing everything.
        logger.info("classroom_coursework_forbidden used_classroom=true course_id=%s", course_id)
        return []
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
        materials = _normalize_materials(w.get("materials"))
        attachments = [AttachmentLink(title=m["title"], url=m["url"]) for m in materials if isinstance(m.get("url"), str)]

        # Append attachments into description (schema stays stable).
        desc_text = str(desc) if isinstance(desc, str) else None
        if materials:
            attachments_block = "\n".join([f"- {m['title']}: {m['url']}" for m in materials])
            extra = f"\n\nAttachments:\n{attachments_block}\n"
            desc_text = (desc_text or "")
            desc_text = (desc_text + extra).strip()

        # Prefer a direct attachment URL if present; otherwise keep the Classroom alternateLink.
        if materials and isinstance(materials[0].get("url"), str):
            url = materials[0]["url"]
        # Classroom doesn't provide estimated duration; leave None.
        out.append(
            Assignment(
                id=str(wid),
                title=str(title),
                dueDate=due_iso,
                courseName=course_name,
                description=desc_text,
                url=str(url) if isinstance(url, str) else None,
                estimatedMinutes=None,
                attachments=attachments or None,
            )
        )
    return out


def _normalize_materials(materials: object) -> list[dict]:
    """
    Convert Google Classroom courseWork.materials[] into a small list of {title,url}.
    We keep schema stable by embedding this in Assignment.description and picking a primary Assignment.url.
    """
    if not isinstance(materials, list):
        return []
    out: list[dict] = []
    for m in materials:
        if not isinstance(m, dict):
            continue

        # Link
        link = m.get("link")
        if isinstance(link, dict):
            url = link.get("url")
            title = link.get("title") or "Link"
            if isinstance(url, str):
                out.append({"title": str(title), "url": url})
                continue

        # Drive file
        drive = m.get("driveFile")
        if isinstance(drive, dict):
            drive_file = drive.get("driveFile")
            if isinstance(drive_file, dict):
                url = drive_file.get("alternateLink") or drive_file.get("webViewLink")
                title = drive_file.get("title") or "Drive file"
                if isinstance(url, str):
                    out.append({"title": str(title), "url": url})
                    continue

        # YouTube
        yt = m.get("youtubeVideo")
        if isinstance(yt, dict):
            url = yt.get("alternateLink")
            title = yt.get("title") or "YouTube"
            if isinstance(url, str):
                out.append({"title": str(title), "url": url})
                continue

        # Form
        form = m.get("form")
        if isinstance(form, dict):
            url = form.get("formUrl")
            title = form.get("title") or "Form"
            if isinstance(url, str):
                out.append({"title": str(title), "url": url})
                continue

    # Keep it small for prompt size.
    return out[:5]


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


