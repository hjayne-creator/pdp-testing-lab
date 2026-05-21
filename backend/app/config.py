from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    xai_api_key: str | None = None
    serpapi_api_key: str | None = None
    firecrawl_api_key: str | None = None
    firecrawl_wait_for_ms: int | None = Field(default=None, ge=0)
    firecrawl_timeout_ms: int = Field(default=120_000, ge=5_000)
    firecrawl_pdf_timeout_ms: int = Field(default=300_000, ge=10_000)
    firecrawl_pdf_retry_timeout_ms: int = Field(default=600_000, ge=10_000)

    database_url: str = "sqlite:///./lab.db"
    app_host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("APP_HOST", "HOST"))
    app_port: int = Field(default=8000, validation_alias=AliasChoices("APP_PORT", "PORT"))
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    auth_username: str = "admin"
    auth_password: str | None = None
    auth_session_secret: str | None = None
    auth_session_ttl_seconds: int = Field(default=60 * 60 * 12, ge=60)
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_cookie_domain: str | None = None

    serpapi_country: str = "us"
    serpapi_language: str = "en"
    serpapi_cost_usd: float = 0.01
    firecrawl_cost_usd: float = 0.01
    max_run_seconds: int = Field(default=180, ge=30)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
