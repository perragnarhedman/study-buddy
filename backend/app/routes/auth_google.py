from __future__ import annotations

import base64
import hashlib
import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.core.auth import issue_session_token
from app.core.config import get_settings
from app.core.db import upsert_tokens
from app.services.pkce_store import pkce_store

router = APIRouter()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _new_state() -> str:
    return _b64url(os.urandom(24))


def _new_verifier() -> str:
    # RFC 7636: 43-128 chars; use urlsafe chars.
    return _b64url(os.urandom(48))


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return _b64url(digest)


@router.get("/auth/google/start")
def google_start() -> dict:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    state = _new_state()
    verifier = _new_verifier()
    pkce_store.put(state, verifier)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(
            [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/classroom.courses.readonly",
                # Needed to read teacher-assigned coursework as a student in many cases.
                "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
                "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
            ]
        ),
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }

    # httpx.URL supports copy_add_param (singular), not copy_add_params.
    authorization_url = httpx.URL("https://accounts.google.com/o/oauth2/v2/auth")
    for k, v in params.items():
        authorization_url = authorization_url.copy_add_param(k, v)

    # Logging: high-level only, no secrets.
    print("oauth_start used_classroom=true")
    return {"authorization_url": str(authorization_url), "state": state}


@router.get("/auth/google/callback")
async def google_callback(code: Optional[str] = None, state: Optional[str] = None):
    settings = get_settings()
    if not settings.google_client_id or not settings.google_redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    verifier = pkce_store.pop(state)
    if not verifier:
        raise HTTPException(status_code=400, detail="Invalid state")

    token_payload = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
    }
    if settings.google_client_secret:
        token_payload["client_secret"] = settings.google_client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data=token_payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Google token exchange failed")
        tok = r.json()

        access_token = tok.get("access_token")
        refresh_token = tok.get("refresh_token")
        expires_in = tok.get("expires_in")
        token_type = tok.get("token_type")
        scope = tok.get("scope")
        id_token = tok.get("id_token")

        if not access_token:
            raise HTTPException(status_code=502, detail="Google token exchange failed")

        user_id = await _resolve_user_id(client, access_token, id_token=id_token)

    expires_at = int(time.time() + int(expires_in)) if expires_in else None
    upsert_tokens(
        user_id=user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        token_type=token_type,
        scope=scope,
        id_token=id_token,
    )

    session_token = issue_session_token(user_id)
    # Redirect back to iOS deep link.
    return RedirectResponse(url=f"studybuddy://auth?token={session_token}")


async def _resolve_user_id(client: httpx.AsyncClient, access_token: str, *, id_token: Optional[str]) -> str:
    # Prefer "sub" from ID token if present (decode without logging).
    sub = _sub_from_id_token(id_token)
    if sub:
        return sub

    # Fallback: userinfo
    r = await client.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Google user lookup failed")
    data = r.json()
    sub = data.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=502, detail="Google user lookup failed")
    return sub


def _sub_from_id_token(id_token: Optional[str]) -> Optional[str]:
    if not id_token or "." not in id_token:
        return None
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        # pad
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        import json

        obj = json.loads(payload.decode("utf-8"))
        sub = obj.get("sub")
        return sub if isinstance(sub, str) and sub else None
    except Exception:
        return None


