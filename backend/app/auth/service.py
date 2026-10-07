"""Database-backed AuthService; passwords and session tokens are never stored raw."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.contracts import Credentials, CurrentUser, SessionGrant
from app.core.errors import AppError
from app.models import AuthSession, User, utcnow

ITERATIONS = 600_000
SESSION_SECONDS = 86_400


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def _user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email, created_at=user.created_at)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


DUMMY_HASH = password_hash("unavailable-account", "00" * 16)


class DatabaseAuthService:
    def __init__(self, session: Session):
        self.session = session

    def register(self, credentials: Credentials) -> CurrentUser:
        user = User(email=credentials.email, password_hash=password_hash(credentials.password))
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError("registration_unavailable", "Registration could not be completed", 409) from None
        return _user(user)

    def login(self, credentials: Credentials) -> SessionGrant:
        user = self.session.scalar(select(User).where(User.email == credentials.email))
        # Also hash when the account is absent to avoid a fast account-existence oracle.
        expected = user.password_hash if user else DUMMY_HASH
        try:
            scheme, iterations, salt, _ = expected.split("$")
            verified = (scheme == "pbkdf2_sha256" and int(iterations) == ITERATIONS
                        and hmac.compare_digest(password_hash(credentials.password, salt), expected))
        except (ValueError, TypeError):
            verified = False
        if user is None or not verified:
            raise AppError("authentication_required", "Email or password is incorrect", 401)
        token = secrets.token_urlsafe(48)
        expires_at = utcnow() + timedelta(seconds=SESSION_SECONDS)
        self.session.add(AuthSession(user_id=user.id, token_hash=token_hash(token), expires_at=expires_at))
        self.session.commit()
        return SessionGrant(user=_user(user), token=token, expires_at=expires_at)

    def logout(self, token: str) -> None:
        self.session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
        self.session.commit()

    def current_user(self, token: str) -> CurrentUser:
        if not 1 <= len(token) <= 512:
            raise AppError("authentication_required", "Session is invalid or expired", 401)
        user = self.session.scalar(select(User).join(AuthSession).where(
            AuthSession.token_hash == token_hash(token), AuthSession.expires_at > utcnow()))
        if user is None:
            raise AppError("authentication_required", "Session is invalid or expired", 401)
        return _user(user)
