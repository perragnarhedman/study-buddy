from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import AuthContext, require_user_id
from app.models.schemas import Announcement, Assignment, Material
from app.services.classroom import fetch_classroom_announcements, fetch_classroom_assignments, fetch_classroom_materials

router = APIRouter()


@router.get("/classroom/assignments", response_model=list[Assignment])
async def classroom_assignments(ctx: AuthContext = Depends(require_user_id)) -> list[Assignment]:
    try:
        return await fetch_classroom_assignments(ctx.user_id)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Missing or invalid session token")
    except ConnectionError:
        raise HTTPException(status_code=502, detail="Google API unreachable")


@router.get("/classroom/materials", response_model=list[Material])
async def classroom_materials(ctx: AuthContext = Depends(require_user_id)) -> list[Material]:
    try:
        return await fetch_classroom_materials(ctx.user_id)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Missing or invalid session token")
    except ConnectionError:
        raise HTTPException(status_code=502, detail="Google API unreachable")


@router.get("/classroom/announcements", response_model=list[Announcement])
async def classroom_announcements(ctx: AuthContext = Depends(require_user_id)) -> list[Announcement]:
    try:
        return await fetch_classroom_announcements(ctx.user_id)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Missing or invalid session token")
    except ConnectionError:
        raise HTTPException(status_code=502, detail="Google API unreachable")


