"""Security interfaces; select and configure an audited implementation before use."""
from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, encoded_hash: str) -> bool: ...


class SessionStore(Protocol):
    """Store a token digest, user ID, expiry and revocation; never plaintext passwords."""

    def revoke(self, token: str) -> None: ...
    def resolve_user_id(self, token: str) -> str | None: ...
