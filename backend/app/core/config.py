from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./singnalx.db"
    provider_mode: str = "mock"
    cors_origins: str = "http://localhost:3000"
    auth_cookie_name: str = "singnalx_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_lifetime_seconds: int = 604800
    worker_poll_seconds: float = 1
    heartbeat_timeout_seconds: int = 120
    agent_request_timeout_seconds: int = Field(default=30, validation_alias="OPENAI_TIMEOUT_SECONDS", ge=1, le=120)

    @model_validator(mode="after")
    def validate_cookie_security(self):
        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true when AUTH_COOKIE_SAMESITE=none")
        required_heartbeat = self.agent_request_timeout_seconds * 2 + 30
        if self.heartbeat_timeout_seconds < required_heartbeat:
            raise ValueError(
                "HEARTBEAT_TIMEOUT_SECONDS must be at least 2 * OPENAI_TIMEOUT_SECONDS + 30 "
                "to allow the provider repair request to finish"
            )
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
