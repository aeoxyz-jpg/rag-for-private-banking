"""Backend-neutral graph export: nodes.jsonl + edges.jsonl (+ graph.graphml).
JSONL loads into NetworkX today and KuzuDB/Neo4j later; GraphML is best-effort (scalar props)."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def export_graph(g: nx.MultiDiGraph, out_dir: Path) -> dict[str, int]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "nodes.jsonl").open("w") as f:
        for nid, d in g.nodes(data=True):
            rec = {"id": nid, "label": d["label"],
                   "props": {k: v for k, v in d.items() if k != "label"}}
            f.write(json.dumps(rec, default=str) + "\n")
    with (out / "edges.jsonl").open("w") as f:
        for u, v, d in g.edges(data=True):
            rec = {"src": u, "dst": v, "type": d["type"],
                   "props": {k: val for k, val in d.items() if k != "type"}}
            f.write(json.dumps(rec, default=str) + "\n")
    gm = nx.MultiDiGraph()
    for nid, d in g.nodes(data=True):
        gm.add_node(nid, label=d["label"], name=str(d.get("name", "")))
    for u, v, d in g.edges(data=True):
        gm.add_edge(u, v, type=d["type"])
    nx.write_graphml(gm, out / "graph.graphml")
    return {"nodes": g.number_of_nodes(), "edges": g.number_of_edges()}
