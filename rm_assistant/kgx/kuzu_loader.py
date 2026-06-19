"""Build/connect an embedded KùzuDB from the backend-neutral graph export. Generic schema:
Node(id,label,name) + Rel(type,percent) so Cypher can filter by type and do var-length paths."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import kuzu

from .. import config


def connect(db_path: Path = config.WEALTH_KUZU) -> kuzu.Connection:
    return kuzu.Connection(kuzu.Database(str(db_path)))


def load_kuzu(export_dir: Path = config.WEALTH_GRAPH_DIR,
              db_path: Path = config.WEALTH_KUZU) -> dict[str, int]:
    db_path = Path(db_path)
    if db_path.exists():
        shutil.rmtree(db_path) if db_path.is_dir() else db_path.unlink()
    conn = kuzu.Connection(kuzu.Database(str(db_path)))
    conn.execute("CREATE NODE TABLE Node(id STRING, label STRING, name STRING, PRIMARY KEY(id))")
    conn.execute("CREATE REL TABLE Rel(FROM Node TO Node, type STRING, percent DOUBLE)")

    n_nodes = 0
    for line in open(Path(export_dir) / "nodes.jsonl"):
        d = json.loads(line)
        conn.execute("CREATE (:Node {id: $id, label: $label, name: $name})",
                     {"id": d["id"], "label": d["label"],
                      "name": str(d.get("props", {}).get("name", ""))})
        n_nodes += 1
    n_rels = 0
    for line in open(Path(export_dir) / "edges.jsonl"):
        d = json.loads(line)
        conn.execute(
            "MATCH (a:Node {id: $s}), (b:Node {id: $d}) "
            "CREATE (a)-[:Rel {type: $t, percent: $p}]->(b)",
            {"s": d["src"], "d": d["dst"], "t": d["type"],
             "p": float(d.get("props", {}).get("percent", 0.0))})
        n_rels += 1
    return {"nodes": n_nodes, "rels": n_rels}
