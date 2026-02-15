from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional


DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=32)
def _load_text_cached(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_text(name: str, *, prompts_dir: Optional[Path] = None) -> str:
    """
    Hot-reload prompt files from disk (read on each call).
    """
    prompts_dir = prompts_dir or DEFAULT_PROMPTS_DIR
    path = prompts_dir / name
    from app.core.config import get_settings

    settings = get_settings()
    if settings.prompts_hot_reload:
        return path.read_text(encoding="utf-8")
    return _load_text_cached(str(path.resolve()))


def render_template(template: str, variables: Dict[str, str]) -> str:
    """
    Render {placeholders} without treating JSON braces as formatting tokens.

    We only replace placeholders that look like identifiers, e.g. {user_message}.
    Other braces (like JSON objects) are left untouched.
    """

    pattern = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    def repl(m: re.Match) -> str:
        key = m.group(1)
        return variables.get(key, m.group(0))

    return pattern.sub(repl, template)


