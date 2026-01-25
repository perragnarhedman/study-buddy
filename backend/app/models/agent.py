from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CoachDecision(BaseModel):
    assistant_text: str
    selected_plan_item_id: str
    # Optional: when the student indicates they've completed something.
    # If provided, backend will persist done state for that plan item's sourceAssignmentId.
    mark_done_plan_item_id: Optional[str] = None
    # 2-letter language code of assistant_text (e.g. "sv", "en").
    reply_language: str
    # Grounding: short snippets (or attachment titles) quoted from candidate description/title/url
    # that justify the chosen next step. Used to prevent hallucinated details.
    evidence: Optional[str] = None


