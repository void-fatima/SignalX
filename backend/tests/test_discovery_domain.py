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
