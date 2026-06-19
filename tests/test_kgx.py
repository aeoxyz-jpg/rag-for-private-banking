"""Network-free checks for the KG experiment harness (kgx). Requires the data layer built
(scripts/build/build_wealth_graph.py); tests that need it skip cleanly when it's absent."""
import json
from pathlib import Path

import pytest

from rm_assistant import config

_EXPORT = config.WEALTH_GRAPH_DIR


def _export_ready():
    return (_EXPORT / "nodes.jsonl").exists() and (_EXPORT / "edges.jsonl").exists()


def test_kuzu_loader_round_trips(tmp_path):
    if not _export_ready():
        pytest.skip("graph export missing (run scripts/build/build_wealth_graph.py)")
    from rm_assistant.kgx import kuzu_loader
    dbp = tmp_path / "g.kuzu"
    kuzu_loader.load_kuzu(_EXPORT, dbp)
    conn = kuzu_loader.connect(dbp)
    n_nodes = list(conn.execute("MATCH (n:Node) RETURN count(n)"))[0][0]
    n_rels = list(conn.execute("MATCH ()-[r:Rel]->() RETURN count(r)"))[0][0]
    exp_nodes = sum(1 for _ in open(_EXPORT / "nodes.jsonl"))
    exp_rels = sum(1 for _ in open(_EXPORT / "edges.jsonl"))
    assert n_nodes == exp_nodes
    assert n_rels == exp_rels
    rows = list(conn.execute(
        "MATCH (a:Node)-[:Rel*1..3]->(b:Node) RETURN b.id LIMIT 5"))
    assert len(rows) >= 1


def test_question_generation():
    truth = config.WEALTH_GRAPH_DIR / "graph_truth.json"
    if not truth.exists():
        pytest.skip("graph_truth.json missing (run scripts/build/build_wealth_graph.py)")
    from rm_assistant.kgx import questions
    qs = questions.generate(truth, n_per_category=5, seed=42)
    cats = {q.category for q in qs}
    assert {"ubo", "household", "k_hop", "controls", "shortest_path"} <= cats
    for q in qs:
        assert q.question and q.gold_kind in ("set", "path")
        assert q.gold
        assert isinstance(q.hop_depth, int) and q.hop_depth >= 1
    qs2 = questions.generate(truth, n_per_category=5, seed=42)
    assert [q.id for q in qs] == [q.id for q in qs2]
    khop = [q for q in qs if q.category == "k_hop"]
    assert khop and all(q.hop_depth in (1, 2, 3) for q in khop)


def test_scorer_set_and_path():
    from rm_assistant.kgx import questions, score
    qset = questions.Question("q1", "ubo", 2, "?", ["P1", "P2"], "set")
    assert score.is_correct(qset, ["P2", "P1"])
    assert not score.is_correct(qset, ["P1"])
    qpath = questions.Question("q2", "shortest_path", 3, "?", ["P1", "E1", "E2", "E3"], "path")
    assert score.is_correct(qpath, ["P1", "X9", "Y2", "E3"])
    assert not score.is_correct(qpath, ["P1", "E3"])
    assert not score.is_correct(qpath, ["P1", "E1", "E2", "Z9"])


class _StubLLM:
    """Returns a fixed query regardless of prompt (for testing solve/execute/extract)."""
    def __init__(self, query):
        self.query = query
        self.name = "stub"

    def complete(self, prompt, system=None, temperature=0.0):
        return self.query


def test_sql_solver_executes_and_extracts():
    if not config.WEALTH_DB.exists():
        pytest.skip("wealth.db (wealth graph) not built")
    from rm_assistant.kgx import solvers, questions
    q = questions.Question("hh", "household", 1, "members of household H1?", [], "set")
    sql = "SELECT party_id FROM banking_identities LIMIT 3"
    res = solvers.SqlSolver(_StubLLM(sql)).solve(q)
    assert res.engine == "sql" and res.valid and res.error is None
    assert isinstance(res.rows, list)
    bad = solvers.SqlSolver(_StubLLM("DELETE FROM nodes")).solve(q)
    assert not bad.valid


def test_cypher_solver_executes_and_extracts(tmp_path):
    if not _export_ready():
        pytest.skip("graph export missing")
    from rm_assistant.kgx import solvers, questions, kuzu_loader
    dbp = tmp_path / "g.kuzu"
    kuzu_loader.load_kuzu(_EXPORT, dbp)
    q = questions.Question("hh", "household", 1, "members?", [], "set")
    cy = "MATCH (n:Node) RETURN n.id LIMIT 3"
    res = solvers.CypherSolver(_StubLLM(cy), db_path=dbp).solve(q)
    assert res.engine == "cypher" and res.valid and res.error is None
    assert len(res.rows) == 3
    bad = solvers.CypherSolver(_StubLLM("CREATE (:Node {id:'x'})"), db_path=dbp).solve(q)
    assert not bad.valid


def test_runner_scores_both_engines_and_modes(tmp_path):
    if not (config.WEALTH_DB.exists() and _export_ready()):
        pytest.skip("data layer not built")
    from rm_assistant.kgx import runner, questions, kuzu_loader
    dbp = tmp_path / "g.kuzu"
    kuzu_loader.load_kuzu(_EXPORT, dbp)
    # a household question with params so the oracle mode can build its query
    q = questions.Question("hh-H1", "household", 1, "members of H1?", [], "set", {"household": "H1"})
    sql_llm = _StubLLM("SELECT node_id FROM nodes LIMIT 1")
    cy_llm = _StubLLM("MATCH (n:Node) RETURN n.id LIMIT 1")
    recs = runner.run([q], sql_llm=sql_llm, cypher_llm=cy_llm, kuzu_path=dbp, samples=2)
    assert {r["engine"] for r in recs} == {"sql", "cypher"}
    assert {r["mode"] for r in recs} == {"llm", "oracle"}
    # 2 samples x 2 engines (llm) + 2 engines (oracle) = 6 records
    assert len([r for r in recs if r["mode"] == "llm"]) == 4
    assert len([r for r in recs if r["mode"] == "oracle"]) == 2
    for r in recs:
        assert r["question_id"] == "hh-H1" and "correct" in r and "outcome" in r


def _rec(mode, engine, qid, cat, depth, correct):
    return {"mode": mode, "engine": engine, "question_id": qid, "category": cat,
            "hop_depth": depth, "valid": True, "correct": correct, "outcome": "ok",
            "attempts": 1, "latency_s": 1.0}


def test_verdict_keys_on_oracle():
    from rm_assistant.kgx import report
    # oracle: SQL collapses at 3+, Cypher holds -> justified (regardless of llm numbers)
    recs = [_rec("oracle", "sql", "q3", "ubo", 3, False),
            _rec("oracle", "cypher", "q3", "ubo", 3, True),
            _rec("llm", "sql", "q3", "ubo", 3, True),
            _rec("llm", "cypher", "q3", "ubo", 3, False)]
    agg = report.aggregate(recs)
    assert agg["oracle"]["sql"]["by_depth"]["3+"] == 0.0
    assert agg["oracle"]["cypher"]["by_depth"]["3+"] == 1.0
    assert report.verdict(agg) == "justified"
    # oracle parity at 3+ -> not justified
    recs2 = [_rec("oracle", "sql", "q3", "ubo", 3, True),
             _rec("oracle", "cypher", "q3", "ubo", 3, True)]
    assert report.verdict(report.aggregate(recs2)) == "not_justified"


def test_aggregate_averages_samples():
    from rm_assistant.kgx import report
    # same question, 2 llm samples: one correct one not -> per-question acc 0.5
    recs = [_rec("llm", "sql", "q1", "k_hop", 2, True),
            _rec("llm", "sql", "q1", "k_hop", 2, False)]
    agg = report.aggregate(recs)
    assert agg["llm"]["sql"]["by_depth"]["2"] == 0.5


def test_kgx_modules_import():
    from rm_assistant.kgx import kuzu_loader, questions, score, solvers, runner, report  # noqa: F401


def test_question_params_populated():
    truth = config.WEALTH_GRAPH_DIR / "graph_truth.json"
    if not truth.exists():
        pytest.skip("graph_truth.json missing")
    from rm_assistant.kgx import questions
    qs = questions.generate(truth, n_per_category=3, seed=42)
    for q in qs:
        assert q.params  # every question carries raw targets for oracles
    khop = next(q for q in qs if q.category == "k_hop")
    assert "party" in khop.params and "k" in khop.params


def test_oracles_are_query_strings():
    from rm_assistant.kgx import oracles, questions
    q = questions.Question("k", "k_hop", 2, "?", [], "set", {"party": "P1", "k": 2})
    assert "P1" in oracles.sql_oracle(q) and "RECURSIVE" in oracles.sql_oracle(q)
    assert "P1" in oracles.cypher_oracle(q) and "Rel*" in oracles.cypher_oracle(q)
    sp = questions.Question("p", "shortest_path", 3, "?", [], "path", {"a": "P1", "b": "E1"})
    assert "SHORTEST" in oracles.cypher_oracle(sp)
