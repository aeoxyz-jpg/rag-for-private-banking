"""Network-free checks for M4 composition (router internals + metric binding + consistency)."""
import pytest

from rm_assistant import config, db, ontology
from rm_assistant.retrieval import router, semantic


def test_extract_client_id():
    assert router._extract_client_id("brief for client 980", None) == 980
    assert router._extract_client_id("client #4521 summary", None) == 4521
    assert router._extract_client_id("how many UHNW clients?", None) is None
    assert router._extract_client_id("anything", 77) == 77


def test_metric_binds_only_present_params():
    assert ontology.metric_binds(ontology.metric_sql("aum")) == {}  # no params
    b = ontology.metric_binds(ontology.metric_sql("days_since_contact"))
    assert "as_of" in b and "start" not in b


def test_governed_aum_consistency():
    if not config.DB_PATH.exists():
        pytest.skip("warehouse not built")
    _, rows = semantic.run_metric("aum", where="aum > 1000000", limit=10000)
    direct = db.connect(readonly=True).execute(
        f"SELECT COUNT(*) FROM ({ontology.metric_sql('aum')}) WHERE aum>1000000").fetchone()[0]
    assert len(rows) == direct  # one governed definition, one number
