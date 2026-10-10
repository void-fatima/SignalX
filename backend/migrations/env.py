from alembic import context
from app.db.session import engine
from app.models import Base
from app.discovery import models as discovery_models  # noqa: F401
from app.integrations.telegram import models as telegram_models  # noqa: F401

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
