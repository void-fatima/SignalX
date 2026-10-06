from sqlalchemy import text


def test_readiness_accepts_current_alembic_head_and_rejects_stale_revision(client, factory):
    with factory() as session:
        session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0003')"))
        session.commit()

    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "revision": "0003"}

    with factory() as session:
        session.execute(text("UPDATE alembic_version SET version_num = '0002'"))
        session.commit()
    stale = client.get("/api/v1/ready")
    assert stale.status_code == 503
    assert stale.json()["error"]["code"] == "not_ready"
