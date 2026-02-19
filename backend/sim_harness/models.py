from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Language = Literal["sv", "en"]


class Persona(BaseModel):
    grade: Optional[int] = None
    motivation: Optional[str] = None  # e.g. "low|medium|high"
    attention: Optional[str] = None  # e.g. "distracted|focused"
    style: Optional[str] = None  # e.g. "short|chatty"


class ScenarioConstraints(BaseModel):
    time_available_minutes: Optional[int] = None
    max_turns: int = 8


class ScenarioExpected(BaseModel):
    """
    Minimal expectations for v1. Keep lightweight and extensible.
    """

    # If set, we expect the coach to select some assignment id at least once in the run.
    require_any_selection: bool = False
    # If set, we expect the coach to NOT select an assignment (overview/greeting).
    require_no_selection: bool = False
    # If set, the final coach turn must select this assignment id.
    expected_selected_assignment_id: Optional[str] = None
    # If set, validate expected_selected_assignment_id on this specific coach turn index (0-based).
    # If omitted, we validate on the final coach turn for backward compatibility.
    expected_selected_assignment_id_turn: Optional[int] = None
    # Coach must not select any of these assignment ids on the final coach turn.
    forbidden_selected_assignment_ids: List[str] = Field(default_factory=list)
    # If set, the final coach turn must mark this assignment as done.
    expected_mark_done_assignment_id: Optional[str] = None
    # If set, validate expected_mark_done_assignment_id on this specific coach turn index (0-based).
    # If omitted, we validate on the final coach turn for backward compatibility.
    expected_mark_done_assignment_id_turn: Optional[int] = None
    # If set, the final coach turn must reply in this language.
    expected_reply_language: Optional[Language] = None
    # If set, the final coach assistant_text must contain all of these substrings.
    assistant_text_must_contain: List[str] = Field(default_factory=list)
    # If set, the final coach assistant_text must NOT contain any of these substrings.
    assistant_text_forbidden_substrings: List[str] = Field(default_factory=list)
    # If set, limit number of question marks in final coach assistant_text.
    max_question_marks: Optional[int] = None


class Scenario(BaseModel):
    scenario_id: str
    title: str
    language: Language = "en"
    persona: Persona = Field(default_factory=Persona)
    constraints: ScenarioConstraints = Field(default_factory=ScenarioConstraints)
    # Raw Classroom-style assignments (source of truth for coach).
    assignments: List[Dict[str, Any]]
    initial_user_message: str
    # Optional scripted user messages (turn-by-turn). If provided, replaces the student simulator.
    user_messages: Optional[List[str]] = None
    expected: ScenarioExpected = Field(default_factory=ScenarioExpected)


class RunConfig(BaseModel):
    """
    Runner configuration.
    Keep defaults small so local iteration is cheap.
    """

    suite: str = "quick"
    max_turns: int = 8
    max_retries: int = 1  # be-sim.13 default
    use_openai_coach: bool = True
    use_openai_judge: bool = False
    enforce_expected: bool = True
    output_dir: str = "sim_runs"
    created_at_iso: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


