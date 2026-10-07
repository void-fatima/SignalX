from alembic import context
from app.models import Base
from app.integrations.telegram import models as telegram_models

def migrate(connection):
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # SQLite table rebuilds require this outside a transaction. Validate every FK afterwards.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    try:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        if sqlite:
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone()
            if violations:
                raise RuntimeError("Migration foreign-key integrity check failed")
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


connection = context.config.attributes.get("connection")
if connection is not None:
    migrate(connection)
else:
    from app.db.session import engine
    with engine.connect() as connection:
        migrate(connection)
