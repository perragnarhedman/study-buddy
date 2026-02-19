from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # We load `.env` opportunistically in `get_settings()` so environments that
    # disallow reading `.env` (e.g., some sandboxes) can still run.
    model_config = SettingsConfigDict()

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Keep this as a string so .env can use a simple comma-separated list.
    # (pydantic-settings treats List[...] as a "complex" type and expects JSON in env vars)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Phase 4/5
    google_client_id: str = ""
    google_client_secret: str = ""  # optional depending on OAuth client type
    google_redirect_uri: str = ""
    session_secret: str = ""
    sqlite_path: str = "backend.sqlite3"
    sqlite_timeout_seconds: float = 10.0
    sqlite_wal_enabled: bool = True
    sqlite_synchronous_normal: bool = True
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-5.2"
    openai_plan_model: str = "gpt-5-mini"
    openai_chat_timeout_seconds: float = 20.0
    # Planning calls can take longer than coaching decisions; keep a generous default.
    openai_plan_timeout_seconds: float = 30.0
    prompts_hot_reload: bool = True

    # Debug export (chat trace + prompts)
    debug_export_enabled: bool = False
    debug_export_dir: str = "debug_exports"

    # Classroom fetch controls.
    classroom_max_concurrency: int = 5
    classroom_cache_ttl_seconds: int = 20

    # OAuth PKCE controls.
    oauth_pkce_ttl_seconds: int = 600

    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Tests should be deterministic and must not accidentally read developer
    # secrets or local debug flags from `.env`.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return Settings(classroom_cache_ttl_seconds=0)
    try:
        return Settings(_env_file=".env", _env_file_encoding="utf-8")
    except OSError:
        # `.env` missing or unreadable; fall back to real env vars + defaults.
        return Settings()


