"""Fast, network-free checks for the M2 pillars (guardrails + fusion + BM25 index)."""
import pytest

from rm_assistant import config, db
from rm_assistant.retrieval import sql_pillar, vector_pillar


def test_sql_validate_blocks_writes():
    assert sql_pillar.validate("SELECT 1") is None
    assert sql_pillar.validate("WITH x AS (SELECT 1) SELECT * FROM x") is None
    assert sql_pillar.validate("DELETE FROM clients") is not None
    assert sql_pillar.validate("DROP TABLE clients") is not None
    assert sql_pillar.validate("SELECT 1; SELECT 2") is not None  # single statement only


def test_rrf_orders_by_consensus():
    # b is rank-0 in both lists -> unambiguous winner over items appearing once
    ranked = vector_pillar._rrf([["b", "a", "c"], ["b", "d", "e"]])
    assert ranked[0] == "b"
    assert set(ranked) == {"a", "b", "c", "d", "e"}


def test_bm25_index_searches():
    if not config.DB_PATH.exists():
        pytest.skip("warehouse not built")
    conn = db.connect(readonly=True)
    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='documents_fts'").fetchone()
    if not has_fts:
        conn.close()
        pytest.skip("FTS index not built (run scripts/build/build_fts.py)")
    hits = vector_pillar._bm25(conn, "retirement pension savings", 5, None, None)
    conn.close()
    assert isinstance(hits, list)
