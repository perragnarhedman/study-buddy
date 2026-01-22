from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional


DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_text(name: str, *, prompts_dir: Optional[Path] = None) -> str:
    """
    Hot-reload prompt files from disk (read on each call).
    """
    prompts_dir = prompts_dir or DEFAULT_PROMPTS_DIR
    path = prompts_dir / name
    return path.read_text(encoding="utf-8")


def render_template(template: str, variables: Dict[str, str]) -> str:
    # Keep it simple and predictable for prompt iteration.
    return template.format(**variables)


