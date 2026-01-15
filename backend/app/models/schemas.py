from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


Role = Literal["user", "assistant"]
PlanStatus = Literal["todo", "doing", "done"]


class ChatMessage(BaseModel):
    id: str
    role: Role
    text: str
    timestamp: str  # ISO8601


class Assignment(BaseModel):
    id: str
    title: str
    dueDate: Optional[str] = None  # ISO8601
    courseName: str
    description: Optional[str] = None
    url: Optional[str] = None
    estimatedMinutes: Optional[int] = None


class PlanItem(BaseModel):
    id: str
    title: str
    dueDate: Optional[str] = None  # ISO8601
    estimatedMinutes: Optional[int] = None
    status: PlanStatus
    sourceAssignmentId: Optional[str] = None


class WeeklyPlan(BaseModel):
    weekStart: str  # ISO8601 date (YYYY-MM-DD)
    items: List[PlanItem]


class ChatSendRequest(BaseModel):
    user_message: str
    current_plan: Optional[WeeklyPlan] = None


class ChatSendResponse(BaseModel):
    assistant_message: ChatMessage
    best_next_action: Optional[PlanItem] = None


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def week_start_iso(d: Optional[date] = None) -> str:
    d = d or date.today()
    start = d.fromordinal(d.toordinal() - d.weekday())  # Monday
    return start.isoformat()


def new_id() -> str:
    return str(uuid4())


