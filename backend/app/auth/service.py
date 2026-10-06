"""Database-backed authentication and server-side revocable sessions."""
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.contracts import CurrentUser, Credentials, SessionGrant
from app.auth.security import ScryptPasswordHasher, SessionStore
from app.core.config import settings
from app.core.errors import AppError
from app.models import User, UserSession, utcnow


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
        if user is None or not self.password_hasher.verify(credentials.password, user.password_hash):
            raise AppError("invalid_credentials", "Email or password is incorrect", 401)

        token = SessionStore.new_token()
        expires_at = utcnow() + timedelta(seconds=settings().session_lifetime_seconds)
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
