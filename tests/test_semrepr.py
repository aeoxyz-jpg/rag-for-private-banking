"""Network-free-ish checks for the semrepr (storage-representation) harness. The full-warehouse
equivalence run lives in scripts/eval/run_semrepr_eval.py; DB-dependent tests skip when data/rm.db is absent."""
import pytest

from rm_assistant import config


def _db_ready():
    return config.DB_PATH.exists()


def test_dbt_compile_structure_and_composition():
    from rm_assistant.semrepr import dbt_repr
    specs = dbt_repr.load()
    assert {"aum", "days_since_contact", "net_new_money", "share_of_wallet", "churn_risk"} <= set(specs)
    # simple metric: generated SELECT over its source, no string-substitution placeholder
    aum = dbt_repr.compile_sql("aum")
    assert "FROM accounts a" in aum and "AS aum" in aum and "{{" not in aum
    # ratio composite: references aum's compiled SQL inline (native), not a {{aum}} placeholder
    sow = dbt_repr.compile_sql("share_of_wallet")
    assert "FROM accounts a" in sow and "/ (m.aum + COALESCE(l.debt, 0))" in sow
    assert dbt_repr.composition_kind("share_of_wallet") == "native"
    assert dbt_repr.composition_kind("churn_risk") == "escape"
    assert dbt_repr.composition_kind("aum") == "n/a"


def test_rdf_assemble_and_catalog():
    from rm_assistant.semrepr import rdf_repr
    assert set(rdf_repr.metrics()) == {"aum", "days_since_contact", "net_new_money",
                                       "share_of_wallet", "churn_risk"}
    # composite inlines its dependency's body where the {ref} placeholder sits
    sow = rdf_repr.assemble_sql("share_of_wallet")
    assert "FROM accounts a" in sow and "{aum}" not in sow
    # composition is modeled as a real dependsOn edge (lineage), not a simple metric
    assert rdf_repr.composition_kind("share_of_wallet") == "native-edge"
    assert rdf_repr.composition_kind("churn_risk") == "native-edge"
    assert rdf_repr.composition_kind("aum") == "n/a"


def test_equivalence_on_fixture():
    import sqlite3
    from rm_assistant.semrepr import equivalence
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE accounts (account_id INT, client_id INT, balance REAL)")
    conn.executemany("INSERT INTO accounts VALUES (?,?,?)",
                     [(1, 100, 10.0), (2, 100, 5.0), (3, 200, 20.0)])
    # two SQLs computing the same per-client total -> equivalent
    canonical = "SELECT client_id, SUM(balance) AS v FROM accounts GROUP BY client_id"
    same = "SELECT client_id AS client_id, SUM(balance) AS v FROM accounts GROUP BY client_id"
    diff = "SELECT client_id, SUM(balance)+1 AS v FROM accounts GROUP BY client_id"
    assert equivalence.same_result(conn, canonical, same) is True
    assert equivalence.same_result(conn, canonical, diff) is False


def test_equivalence_full_warehouse():
    if not _db_ready():
        pytest.skip("warehouse not built (scripts/build/build_unified.py)")
    from rm_assistant.semrepr import equivalence
    dbt = equivalence.check("dbt")
    rdf = equivalence.check("rdf")
    assert dbt == {m: True for m in dbt}, f"dbt equivalence failures: {dbt}"
    assert rdf == {m: True for m in rdf}, f"rdf equivalence failures: {rdf}"


def test_catalog_uniform_view():
    from rm_assistant.semrepr import catalog
    base = catalog.catalog("baseline")
    dbt = catalog.catalog("dbt")
    rdf = catalog.catalog("rdf")
    metrics = {"aum", "days_since_contact", "net_new_money", "share_of_wallet", "churn_risk"}
    for c in (base, dbt, rdf):
        assert set(c["metrics"]) == metrics
        assert c["queryable"] in ("yes", "partial", "no")
    # baseline composes composites by string-substitution; dbt has a native ratio; all three are queryable
    assert base["composition"]["share_of_wallet"] == "string-substitution"
    assert dbt["composition"]["share_of_wallet"] == "native"
    assert rdf["composition"]["share_of_wallet"] == "native-edge"
    assert base["queryable"] == "yes" and dbt["queryable"] == "yes" and rdf["queryable"] == "yes"


def test_verdict_rule():
    from rm_assistant.semrepr import report
    # an alternative that passes equivalence, has a native composite, full catalog, within budget -> migrate
    good = {"equivalence_all": True, "native_composites": 1, "queryable": "yes", "verbosity_ratio": 1.2}
    assert report.verdict(good) == "migrate"
    # fails equivalence -> keep regardless
    assert report.verdict({**good, "equivalence_all": False}) == "keep"
    # no native composition gain -> keep
    assert report.verdict({**good, "native_composites": 0}) == "keep"
    # over the verbosity budget -> keep
    assert report.verdict({**good, "verbosity_ratio": 2.0}) == "keep"


def test_axis_scores_shape():
    from rm_assistant.semrepr import report
    eq = {m: True for m in ("aum", "share_of_wallet", "churn_risk")}
    comp = {"aum": "n/a", "share_of_wallet": "native", "churn_risk": "escape"}
    s = report.axis_scores("dbt", eq, comp, queryable="yes", verbosity_lines=30, baseline_lines=25,
                            generates_sql=True)
    assert s["equivalence_all"] is True and s["native_composites"] == 1
    assert s["verbosity_ratio"] == round(30 / 25, 2) and s["dialect"] == "generates"


def test_semrepr_modules_import():
    from rm_assistant.semrepr import dbt_repr, rdf_repr, catalog, equivalence, report  # noqa: F401
