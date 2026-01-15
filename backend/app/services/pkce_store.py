from __future__ import annotations

import time
from typing import Optional


class PKCEStore:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: dict[str, tuple[str, float]] = {}

    def put(self, state: str, verifier: str) -> None:
        self._data[state] = (verifier, time.time() + self.ttl_seconds)

    def pop(self, state: str) -> Optional[str]:
        self._gc()
        item = self._data.pop(state, None)
        if not item:
            return None
        verifier, expires_at = item
        if time.time() > expires_at:
            return None
        return verifier

    def _gc(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._data.items() if now > exp]
        for k in expired:
            self._data.pop(k, None)


pkce_store = PKCEStore()


