"""Typed account and session contracts for the Backend authentication routes."""
from datetime import datetime
from typing import Protocol
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        local, separator, domain = value.partition("@")
        if not separator or not local or not domain or "." not in domain or any(ch.isspace() for ch in value):
            raise ValueError("Enter a valid email address")
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
