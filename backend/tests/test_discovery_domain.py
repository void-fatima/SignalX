from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from app.discovery.schemas import SearchInput, SaveInput

def search(**updates):
    return SearchInput.model_validate({"product_id":uuid4(), "source":"brave", "keywords":"accounting tools", **updates})

@pytest.mark.parametrize("updates", [{"keywords":" "}, {"keywords":"bad\nquery"}, {"limit":0}, {"limit":21}, {"country":"Germany"}, {"extra":"unknown"}])
def test_invalid_search_input(updates):
    with pytest.raises(ValidationError): search(**updates)

@pytest.mark.parametrize("source", ["greenhouse", "lever"])
def test_jobs_require_safe_company_specific_board(source):
    with pytest.raises(ValidationError): SearchInput(product_id=uuid4(),source=source,keywords="finance")
    with pytest.raises(ValidationError): SearchInput(product_id=uuid4(),source=source,keywords="finance",board_slug="../internal")
    assert SearchInput(product_id=uuid4(),source=source,keywords="finance",board_slug="acme").limit == 10

def test_places_requires_location_and_save_requires_unique_ids():
    with pytest.raises(ValidationError): SearchInput(product_id=uuid4(),source="places",keywords="clinics")
    with pytest.raises(ValidationError): SaveInput(search_id=uuid4(),source_ids=["same","same"])

def test_discovery_tables_keep_owner_product_and_source_constraints(factory):
    with factory() as session:
        inspector=inspect(session.bind)
        assert {"discovery_searches","discovery_prospects","discovery_budgets"} <= set(inspector.get_table_names())
        assert {row["referred_table"] for row in inspector.get_foreign_keys("discovery_prospects")} == {"users","products","discovery_searches"}


def test_additive_migration_preserves_existing_profiles(tmp_path):
    import os, sqlite3, subprocess, sys
    from pathlib import Path
    database=tmp_path/"discovery-migration.db"
    env={**os.environ,"DATABASE_URL":f"sqlite:///{database.as_posix()}"}
    def migrate(operation,revision):
        result=subprocess.run([sys.executable,"-m","alembic",operation,revision],cwd=Path(__file__).parents[1],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    migrate("upgrade","0007")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO products (id,created_at,name,description,target_customer,problems_solved,best_fit,not_fit,currency) VALUES ('retained','2026-10-10','Profile','Original description','Owners','[]','[]','[]','USD')")
    for operation,revision in (("upgrade","0008"),("downgrade","0007")):
        migrate(operation,revision)
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT description FROM products WHERE id='retained'").fetchone()==('Original description',)
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert ("discovery_prospects" in tables)==(revision=="0008")
