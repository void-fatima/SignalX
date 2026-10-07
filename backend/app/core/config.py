from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./singnalx.db"
    provider_mode: str = "mock"
    cors_origins: str = "http://localhost:3000"
    worker_poll_seconds: float = 1
    heartbeat_timeout_seconds: int = 120
    auth_cookie_secure: bool = True


@lru_cache
def settings() -> Settings:
    return Settings()
