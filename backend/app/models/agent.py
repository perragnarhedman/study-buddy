from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CoachDecision(BaseModel):
    assistant_text: str
    selected_plan_item_id: Optional[str] = None
    # Optional: when the student indicates they've completed something.
    # If provided, backend will persist done state for that plan item's sourceAssignmentId.
    mark_done_plan_item_id: Optional[str] = None
    # Optional language hint from the model ("sv", "en", etc). Not required.
    reply_language: Optional[str] = None


