"""Light M0 checks. Network/Ollama-dependent tests skip cleanly when unavailable."""
import sqlite3

import pytest

from rm_assistant import config, db


def test_embedder_roundtrip():
    httpx = pytest.importorskip("httpx")
    from rm_assistant.models.factory import get_embedder

    try:
        emb = get_embedder().embed(["hello world", "private banking"])
    except httpx.HTTPError:
        pytest.skip("Ollama not reachable")
    assert len(emb) == 2
    assert len(emb[0]) == len(emb[1]) > 0


def test_berka_raw_loaded():
    if not config.BERKA_RAW_DB.exists():
        pytest.skip("raw Berka not loaded (run scripts/build/load_berka.py)")
    conn = db.connect(config.BERKA_RAW_DB, readonly=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"client", "account", "trans"} <= names


def test_unified_built():
    if not config.DB_PATH.exists():
        pytest.skip("unified warehouse not built (run scripts/build/build_unified.py)")
    conn = db.connect(readonly=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        n_clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        segs = {r[0] for r in conn.execute("SELECT DISTINCT segment FROM clients")}
    finally:
        conn.close()
    assert {"clients", "accounts", "transactions", "holdings", "edges"} <= names
    assert n_clients == 5369
    assert "HNW" in segs or "UHNW" in segs
