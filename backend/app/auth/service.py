"""Database-backed authentication and server-side revocable sessions."""
from datetime import datetime, timedelta
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.contracts import CurrentUser, Credentials, SessionGrant
from app.auth.security import ScryptPasswordHasher, SessionStore
from app.core.config import settings
from app.core.errors import AppError
from app.models import User, UserSession, utcnow


# A valid scrypt hash keeps nonexistent-account logins on the same expensive
# verification path as existing-account logins. This value is not a credential.
_DUMMY_PASSWORD_HASH = (
    "scrypt$16384$8$1$8f3c2a190e7d4b6c5a8f10d3c2b1a0e9$"
    "7d782347cd41c15cfe39abf6bb6394d3a97878bcc20002a276e3639486420fe8"
)


def cleanup_stale_sessions(session: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    result = session.execute(delete(UserSession).where(or_(
        UserSession.revoked_at.is_not(None), UserSession.expires_at <= now,
    )))
    return result.rowcount or 0


def _current_user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email, created_at=user.created_at)


class DatabaseAuthService:
    def __init__(self, session: Session):
        self.session = session
        self.password_hasher = ScryptPasswordHasher()

    def register(self, credentials: Credentials) -> CurrentUser:
        user = User(
            email=credentials.email,
            password_hash=self.password_hasher.hash(credentials.password),
        )
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError("email_already_registered", "An account with this email already exists", 409) from exc
        return _current_user(user)

    def login(self, credentials: Credentials) -> SessionGrant:
        user = self.session.scalar(select(User).where(User.email == credentials.email))
        encoded_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_valid = self.password_hasher.verify(credentials.password, encoded_hash)
        if user is None or not password_valid:
            raise AppError("invalid_credentials", "Email or password is incorrect", 401)

        token = SessionStore.new_token()
        now = utcnow()
        # Opportunistically remove revoked and expired sessions so normal auth
        # traffic does not grow the session table indefinitely.
        cleanup_stale_sessions(self.session, now)
        expires_at = now + timedelta(seconds=settings().session_lifetime_seconds)
        self.session.add(UserSession(
            user_id=user.id,
            token_digest=SessionStore.token_digest(token),
            expires_at=expires_at,
        ))
        self.session.commit()
        return SessionGrant(user=_current_user(user), token=token, expires_at=expires_at)

    def logout(self, token: str) -> None:
        session_record = self.session.scalar(select(UserSession).where(
            UserSession.token_digest == SessionStore.token_digest(token),
            UserSession.revoked_at.is_(None),
        ))
        if session_record is not None:
            session_record.revoked_at = utcnow()
            self.session.commit()

    def current_user(self, token: str) -> CurrentUser:
        now = utcnow()
        session_record = self.session.scalar(select(UserSession).where(
            UserSession.token_digest == SessionStore.token_digest(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        ))
        user = self.session.get(User, session_record.user_id) if session_record else None
        if user is None:
            raise AppError("authentication_required", "A valid login session is required", 401)
        return _current_user(user)
