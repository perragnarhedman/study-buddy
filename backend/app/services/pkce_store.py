from __future__ import annotations

from typing import Optional

from app.core.config import get_settings
from app.core.db import pop_pkce_state, put_pkce_state


class PKCEStore:
    def __init__(self, ttl_seconds: Optional[int] = None) -> None:
        settings = get_settings()
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.oauth_pkce_ttl_seconds

    def put(self, state: str, verifier: str) -> None:
        put_pkce_state(state=state, verifier=verifier, ttl_seconds=self.ttl_seconds)

    def pop(self, state: str) -> Optional[str]:
        return pop_pkce_state(state)


pkce_store = PKCEStore()


