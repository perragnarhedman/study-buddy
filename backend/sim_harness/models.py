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


class Scenario(BaseModel):
    scenario_id: str
    title: str
    language: Language = "en"
    persona: Persona = Field(default_factory=Persona)
    constraints: ScenarioConstraints = Field(default_factory=ScenarioConstraints)
    # Raw Classroom-style assignments (source of truth for coach).
    assignments: List[Dict[str, Any]]
    initial_user_message: str
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
    output_dir: str = "sim_runs"
    created_at_iso: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


