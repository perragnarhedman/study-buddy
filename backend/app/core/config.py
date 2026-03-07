from __future__ import annotations

import os
from functools import lru_cache

from pydantic import model_validator
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
    # Public base URL for this API when deployed (e.g. https://your-service.onrender.com).
    # If set, we can derive google_redirect_uri automatically.
    public_base_url: str = ""
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

    # WhatsApp (Meta Cloud API)
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    # Classroom fetch controls.
    classroom_max_concurrency: int = 5
    classroom_cache_ttl_seconds: int = 20

    # OAuth PKCE controls.
    oauth_pkce_ttl_seconds: int = 600

    @model_validator(mode="after")
    def _derive_oauth_redirect_uri(self) -> "Settings":
        # Keep backwards compatibility: allow explicit GOOGLE_REDIRECT_URI.
        # For hosted deployments, PUBLIC_BASE_URL is easier to configure reliably.
        if not self.google_redirect_uri and self.public_base_url:
            base = self.public_base_url.rstrip("/")
            self.google_redirect_uri = f"{base}/auth/google/callback"
        return self

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


