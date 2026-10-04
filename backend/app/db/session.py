from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings().database_url, **(
    {"connect_args": {"check_same_thread": False}} if settings().database_url.startswith("sqlite") else {}
))
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
