"""Project the canonical graph into SQLite: faithful nodes/relationships + convenience tables."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from .. import config, db
from . import ubo as ubo_mod

_SCHEMA = """
DROP TABLE IF EXISTS nodes;
CREATE TABLE nodes (node_id TEXT PRIMARY KEY, label TEXT, name TEXT, props_json TEXT);
DROP TABLE IF EXISTS relationships;
CREATE TABLE relationships (src_id TEXT, dst_id TEXT, rel_type TEXT, attrs_json TEXT);
DROP TABLE IF EXISTS banking_identities;
CREATE TABLE banking_identities (party_id TEXT, segment TEXT);
DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (account_id TEXT, owner_id TEXT, type TEXT, currency TEXT, balance REAL, opened_at TEXT);
DROP TABLE IF EXISTS ubo;
CREATE TABLE ubo (entity_id TEXT, person_id TEXT, effective_pct REAL, path_json TEXT);
"""


def project_relational(g: nx.MultiDiGraph, db_path: Path = config.WEALTH_DB,
                       ubo_threshold: float = config.WG_UBO_THRESHOLD) -> dict[str, int]:
    if Path(db_path).exists():
        Path(db_path).unlink()
    conn = db.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        node_rows, bi_rows, acct_rows = [], [], []
        for nid, d in g.nodes(data=True):
            props = {k: v for k, v in d.items() if k not in ("label", "name")}
            node_rows.append((nid, d["label"], d.get("name"), json.dumps(props, default=str)))
            for seg in d.get("segments", []):
                bi_rows.append((nid, seg))
            if d["label"] == "Account":
                acct_rows.append((nid, d.get("owner"), d.get("type"), d.get("currency"),
                                  d.get("balance"), d.get("opened_at")))
        rel_rows = [(u, v, d["type"],
                     json.dumps({k: val for k, val in d.items() if k != "type"}, default=str))
                    for u, v, d in g.edges(data=True)]
        conn.executemany("INSERT INTO nodes VALUES (?,?,?,?)", node_rows)
        conn.executemany("INSERT INTO relationships VALUES (?,?,?,?)", rel_rows)
        conn.executemany("INSERT INTO banking_identities VALUES (?,?)", bi_rows)
        conn.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?)", acct_rows)
        ubo_rows = [(r["entity_id"], r["person_id"], r["effective_pct"], json.dumps(r["path"]))
                    for r in ubo_mod.derive_ubo(g, ubo_threshold)]
        conn.executemany("INSERT INTO ubo VALUES (?,?,?,?)", ubo_rows)
        conn.commit()
        return {"nodes": len(node_rows), "relationships": len(rel_rows),
                "banking_identities": len(bi_rows), "accounts": len(acct_rows), "ubo": len(ubo_rows)}
    finally:
        conn.close()
