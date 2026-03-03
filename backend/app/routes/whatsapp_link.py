import time

from fastapi import APIRouter, Depends

from app.core.auth import AuthContext, require_user_id
from app.core.db import create_whatsapp_link_code

router = APIRouter()


@router.post("/whatsapp/link/code")
def whatsapp_link_code(ctx: AuthContext = Depends(require_user_id)) -> dict:
    code, expires_at = create_whatsapp_link_code(user_id=ctx.user_id, ttl_seconds=600, code_len=6)
    return {
        "code": code,
        "expires_at": int(expires_at),
        "expires_in_seconds": max(int(expires_at) - int(time.time()), 0),
    }

