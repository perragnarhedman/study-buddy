from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings


@dataclass(frozen=True)
class AuthContext:
    user_id: str


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET is not set")
    return URLSafeTimedSerializer(settings.session_secret, salt="studybuddy-session")


def issue_session_token(user_id: str) -> str:
    s = _serializer()
    return s.dumps({"user_id": user_id})


def verify_session_token(token: str, *, max_age_seconds: int = 60 * 60 * 24 * 30) -> str:
    s = _serializer()
    try:
        data = s.loads(token, max_age=max_age_seconds)
        user_id = data.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(status_code=401, detail="Invalid session token")
        return user_id
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session token")


def get_optional_user_id(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    try:
        return verify_session_token(token)
    except Exception:
        return None


def require_user_id(authorization: Optional[str] = Header(default=None)) -> AuthContext:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing session token")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing session token")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing session token")
    user_id = verify_session_token(token)
    return AuthContext(user_id=user_id)


