from __future__ import annotations

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
    openai_api_key: str = ""

    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings(_env_file=".env", _env_file_encoding="utf-8")
    except OSError:
        # `.env` missing or unreadable; fall back to real env vars + defaults.
        return Settings()


