from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


CoachIntent = Literal["overview", "recommend", "continue", "clarify", "mark_done"]


class CoachDecision(BaseModel):
    assistant_text: str
    reply_language: str  # 2-letter code, e.g. "sv", "en"
    intent: CoachIntent
    selected_plan_item_id: Optional[str] = None
    # Optional: when the student indicates they've completed something.
    # If provided, backend will persist done state for that plan item's sourceAssignmentId.
    mark_done_plan_item_id: Optional[str] = None
    # Grounding: short snippets (or attachment titles) quoted from candidate description/title/url
    # that justify the chosen next step. Used to prevent hallucinated details.
    evidence: Optional[str] = None
    clarifying_question: Optional[str] = None


