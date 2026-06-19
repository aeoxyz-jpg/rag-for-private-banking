"""Generator-emitted gold answers for relationship queries (independent of any query engine)."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from . import model, ubo as ubo_mod


def emit_ground_truth(g: nx.MultiDiGraph, out_path: Path, threshold: float = 0.25,
                      k_hop_sample: int = 20, path_pairs: int = 20) -> dict:
    undirected = g.to_undirected()

    households = {h: list(g.nodes[h].get("members", []))
                  for h, d in g.nodes(data=True) if d["label"] == "Household"}

    parties = [n for n, d in g.nodes(data=True)
               if d["label"] in ("NaturalPerson", "LegalEntity")]
    sample = parties[:k_hop_sample]
    k_hop = {}
    for p in sample:
        lengths = nx.single_source_shortest_path_length(undirected, p, cutoff=3)
        k_hop[p] = {str(k): sorted(n for n, dist in lengths.items() if dist == k)
                    for k in (1, 2, 3)}

    ubo_rows = ubo_mod.derive_ubo(g, threshold)
    controls = {}
    for r in ubo_rows:
        controls.setdefault(r["person_id"], []).append(r["entity_id"])

    shortest = []
    persons = [n for n, d in g.nodes(data=True) if d["label"] == "NaturalPerson"]
    entities = [n for n, d in g.nodes(data=True) if d["label"] == "LegalEntity"]
    for i in range(min(path_pairs, len(persons), len(entities))):
        a, b = persons[i], entities[i]
        if nx.has_path(undirected, a, b):
            shortest.append({"a": a, "b": b, "path": nx.shortest_path(undirected, a, b)})

    gt = {
        "ubo": ubo_rows,
        "household_members": households,
        "k_hop": k_hop,
        "controls_entities": {p: sorted(set(es)) for p, es in controls.items()},
        "shortest_paths": shortest,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(gt, default=str, indent=1))
    return gt
