from pathlib import Path
from sqlalchemy import text
from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_readiness_accepts_current_alembic_head_and_rejects_stale_revision(client, factory):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    current_head = ScriptDirectory.from_config(config).get_current_head()
    with factory() as session:
        session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        session.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                        {"revision": current_head})
        session.commit()

    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "revision": current_head}

    with factory() as session:
        session.execute(text("UPDATE alembic_version SET version_num = '0002'"))
        session.commit()
    stale = client.get("/api/v1/ready")
    assert stale.status_code == 503
    assert stale.json()["error"]["code"] == "not_ready"
