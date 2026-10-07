"""Shared authentication interface and safe public session/user contracts."""
from datetime import datetime
import re
from typing import Protocol
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128, repr=False, json_schema_extra={"writeOnly": True})

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("A valid email address is required")
        return value


class CurrentUser(BaseModel):
    id: UUID
    email: str
    created_at: datetime


class SessionGrant(BaseModel):
    user: CurrentUser
    token: str = Field(repr=False, exclude=True)
    expires_at: datetime


class AuthService(Protocol):
    """Implement hash verification, expiring sessions, revocation and user lookup."""

    def register(self, credentials: Credentials) -> CurrentUser: ...
    def login(self, credentials: Credentials) -> SessionGrant: ...
    def logout(self, token: str) -> None: ...
    def current_user(self, token: str) -> CurrentUser: ...
