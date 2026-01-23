from __future__ import annotations

from pydantic import BaseModel


class CoachDecision(BaseModel):
    assistant_text: str
    selected_plan_item_id: str


