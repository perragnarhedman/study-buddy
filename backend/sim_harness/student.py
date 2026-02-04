from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class StudentState:
    """
    Minimal state machine:
    - after the coach makes a recommendation (selection), student acknowledges once ("ok"/"ja")
    - then stops
    """

    did_ack: bool = False


def next_user_message(*, lang: str, state: StudentState, coach_selected_assignment_id: Optional[str]) -> Optional[str]:
    if coach_selected_assignment_id and not state.did_ack:
        state.did_ack = True
        return "Okej." if lang == "sv" else "Ok."
    return None


