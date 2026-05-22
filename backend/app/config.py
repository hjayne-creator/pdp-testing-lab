from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


def _discover_env_files() -> tuple[Path, ...]:
    """Load repo-root .env first, then backend/.env (later file wins)."""
    candidates = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")
    return tuple(p for p in candidates if p.is_file())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_discover_env_files(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    xai_api_key: str | None = None
    serpapi_api_key: str | None = None
    firecrawl_api_key: str | None = None

    @staticmethod
    def _coerce_blank_api_key(value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "xai_api_key",
        "serpapi_api_key",
        "firecrawl_api_key",
        mode="before",
    )
    @classmethod
    def _normalize_api_keys(cls, value: object) -> object:
        return cls._coerce_blank_api_key(value)
    firecrawl_wait_for_ms: int | None = Field(default=None, ge=0)
    firecrawl_timeout_ms: int = Field(default=120_000, ge=5_000)
    firecrawl_pdf_timeout_ms: int = Field(default=300_000, ge=10_000)
    firecrawl_pdf_retry_timeout_ms: int = Field(default=600_000, ge=10_000)

    database_url: str = "sqlite:///./lab.db"
    app_host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("APP_HOST", "HOST"))
    app_port: int = Field(default=8000, validation_alias=AliasChoices("APP_PORT", "PORT"))
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("app_port", mode="before")
    @classmethod
    def _coerce_port(cls, value: object) -> object:
        if value == "" or value is None:
            return None
        return value

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

    research_pdf_max_bytes: int = Field(
        default=2_000_000,
        ge=0,
        description="Skip Firecrawl on PDFs larger than this (HEAD Content-Length). 0 disables.",
    )
    research_pdf_max_chars: int = Field(default=25_000, ge=1_000)
    research_page_max_chars: int = Field(default=50_000, ge=1_000)
    research_evidence_max_chars: int = Field(default=12_000, ge=1_000)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def env_file_paths(self) -> list[Path]:
        return list(_discover_env_files())

    def missing_api_key_hint(self, env_name: str) -> str:
        paths = self.env_file_paths
        parts = [
            f"Set {env_name} in backend/.env or the repository root .env for local development.",
            "On Railway or other hosts, add the variable in the service dashboard — .env files are not deployed.",
            "Restart the backend after changing local .env files.",
        ]
        if paths:
            parts.append(f"Loaded env files: {', '.join(str(p) for p in paths)}.")
        else:
            parts.append(f"No .env found at {_BACKEND_DIR / '.env'} or {_REPO_ROOT / '.env'}.")
        return " ".join(parts)

    @model_validator(mode="after")
    def _cross_origin_cookie_defaults(self) -> "Settings":
        """Frontend and API on different hosts need SameSite=None session cookies."""
        if not self.auth_password:
            return self
        cross_origin = any(
            origin.startswith("https://")
            and "localhost" not in origin
            and "127.0.0.1" not in origin
            for origin in self.cors_origin_list
        )
        if cross_origin:
            if self.auth_cookie_samesite == "lax":
                self.auth_cookie_samesite = "none"
            if not self.auth_cookie_secure:
                self.auth_cookie_secure = True
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
