from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CoachDecision(BaseModel):
    assistant_text: str
    selected_plan_item_id: str
    # Optional: when the student indicates they've completed something.
    # If provided, backend will persist done state for that plan item's sourceAssignmentId.
    mark_done_plan_item_id: Optional[str] = None


