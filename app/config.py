"""Settings loaded from environment variables and .env files."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(..., description="Async Postgres URL")
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_allowed_origins: str = Field(
        default="",
        description="Comma-separated list of allowed CORS origins",
    )
    cookie_secure: bool = Field(
        default=False,
        description="Set Secure on session cookies. False for local HTTP.",
    )
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="SameSite setting for session cookies.",
    )
    session_lifetime_hours: int = Field(
        default=24,
        description="Sliding session expiry in hours.",
    )
    cookie_name: str = Field(default="crewline_session")
    pm_initial_password: str | None = Field(default=None)
    agent_be_initial_key: str | None = Field(default=None)
    agent_fe_initial_key: str | None = Field(default=None)
    agent_architect_initial_key: str | None = Field(default=None)
    agent_qa_initial_key: str | None = Field(default=None)
    storage_endpoint_url: str = Field(default="http://localhost:9000")
    storage_access_key: str = Field(default="minioadmin")
    storage_secret_key: str = Field(default="minioadmin")
    storage_bucket: str = Field(default="crewline-attachments")
    storage_region: str = Field(default="us-east-1")
    storage_addressing_style: Literal["path", "virtual"] = Field(default="path")
    attachment_max_size_bytes: int = Field(default=25 * 1024 * 1024)
    attachment_upload_url_ttl_seconds: int = Field(default=15 * 60)
    attachment_download_url_ttl_seconds: int = Field(default=15 * 60)
    attachment_pending_cleanup_age_hours: int = Field(default=24)
    github_app_id: str | None = Field(default=None)
    github_app_client_id: str | None = Field(default=None)
    github_app_client_secret: str | None = Field(default=None)
    github_app_private_key: str | None = Field(default=None)
    github_app_name: str = Field(default="Crewline")
    github_frontend_redirect_url: str = Field(
        default="http://localhost:5173/settings?github=connected"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_allowed_origins:
            return []
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
