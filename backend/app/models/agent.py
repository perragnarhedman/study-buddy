from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CoachDecision(BaseModel):
    assistant_text: str
    # New (be-crg): when candidates are raw Classroom assignments, the model selects an assignment id.
    selected_assignment_id: Optional[str] = None
    # Optional reopen action for a reference-only assignment the student wants to work on again.
    reopen_assignment_id: Optional[str] = None
    selected_plan_item_id: Optional[str] = None
    # Optional: when the student indicates they've completed something.
    # If provided, backend will persist done state for that plan item's sourceAssignmentId.
    mark_done_plan_item_id: Optional[str] = None
    # New (be-crg): allow marking completion by assignment id directly.
    mark_done_assignment_id: Optional[str] = None
    # Optional language hint from the model ("sv", "en", etc). Not required.
    reply_language: Optional[str] = None


